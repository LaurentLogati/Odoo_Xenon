# -*- coding: utf-8 -*-
import base64
import io
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class AccountStockVariationWizard(models.TransientModel):
    _name = 'account.stock.variation.wizard'
    _description = "Analyse de variation de stock (achats / ventes)"

    date_from = fields.Date(string="Date de début", required=True)
    date_to = fields.Date(string="Date de fin", required=True)
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, required=True)
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        string="Codes analytiques",
        help="Si renseigné, seules les lignes d'écriture liées à AU MOINS UN de ces "
             "codes analytiques sont prises en compte.",
    )
    line_ids = fields.One2many(
        'account.stock.variation.line', 'wizard_id', string="Résultat")

    # -------------------------------------------------------------------------
    # Calcul
    # -------------------------------------------------------------------------

    def _get_base_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
            ('display_type', '=', 'product'),
            ('product_id', '!=', False),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.analytic_account_ids:
            domain.append(('analytic_distribution', 'in', self.analytic_account_ids.ids))
        return domain

    def action_compute(self):
        """Calcule, pour chaque article acheté et/ou vendu sur la période, les quantités
        achetées/vendues, le coût unitaire d'achat (ou le coût de la fiche article si aucun
        achat sur la période) et la variation de stock calculée qui en découle."""
        self.ensure_one()

        if not self.date_from or not self.date_to:
            raise UserError(_("Veuillez renseigner la date de début et la date de fin."))
        if self.date_from > self.date_to:
            raise UserError(_("La date de début doit être antérieure ou égale à la date de fin."))

        self.line_ids.unlink()

        AccountMoveLine = self.env['account.move.line']
        base_domain = self._get_base_domain()

        purchase_lines = AccountMoveLine.search(
            base_domain + [('move_id.move_type', 'in', ('in_invoice', 'in_refund'))])
        sale_lines = AccountMoveLine.search(
            base_domain + [('move_id.move_type', 'in', ('out_invoice', 'out_refund'))])

        # Achats : on distingue les lignes de facture (base du coût unitaire et du test
        # "pas d'achat sur la période") des lignes d'avoir (qui ne viennent que diminuer
        # la quantité nette achetée).
        purchase_invoice_qty = defaultdict(float)
        purchase_invoice_value = defaultdict(float)
        purchase_refund_qty = defaultdict(float)
        for line in purchase_lines:
            product_id = line.product_id.id
            if line.move_id.move_type == 'in_invoice':
                purchase_invoice_qty[product_id] += line.quantity
                purchase_invoice_value[product_id] += line.price_subtotal
            else:  # in_refund
                purchase_refund_qty[product_id] += line.quantity

        # Ventes : quantité vendue nette (factures - avoirs).
        sale_invoice_qty = defaultdict(float)
        sale_refund_qty = defaultdict(float)
        for line in sale_lines:
            product_id = line.product_id.id
            if line.move_id.move_type == 'out_invoice':
                sale_invoice_qty[product_id] += line.quantity
            else:  # out_refund
                sale_refund_qty[product_id] += line.quantity

        product_ids = set(purchase_invoice_qty) | set(purchase_refund_qty) \
            | set(sale_invoice_qty) | set(sale_refund_qty)

        products_by_id = {
            p.id: p for p in self.env['product.product'].browse(product_ids)
            .with_company(self.company_id)
        }

        lines_vals = []
        for product_id in product_ids:
            product = products_by_id[product_id]
            rounding = product.uom_id.rounding

            qty_purchased = purchase_invoice_qty[product_id] - purchase_refund_qty[product_id]
            qty_sold = sale_invoice_qty[product_id] - sale_refund_qty[product_id]

            has_purchase = not float_is_zero(
                purchase_invoice_qty[product_id], precision_rounding=rounding)
            if has_purchase:
                cost_unit = purchase_invoice_value[product_id] / purchase_invoice_qty[product_id]
            else:
                cost_unit = product.standard_price

            stock_variation = (qty_purchased - qty_sold) * cost_unit

            lines_vals.append((0, 0, {
                'product_id': product_id,
                'qty_purchased': qty_purchased,
                'qty_sold': qty_sold,
                'cost_unit': cost_unit,
                'cost_from_product': not has_purchase,
                'stock_variation': stock_variation,
            }))

        self.line_ids = lines_vals

        action = self.env['ir.actions.act_window']._for_xml_id(
            'Xenon_analyse_stock_compta.action_account_stock_variation_wizard')
        action['res_id'] = self.id
        return action

    # -------------------------------------------------------------------------
    # Impressions / exports
    # -------------------------------------------------------------------------

    def action_print_report(self):
        """Génère le rapport PDF."""
        self.ensure_one()
        return self.env.ref(
            'Xenon_analyse_stock_compta.action_report_account_stock_variation'
        ).report_action(self)

    def action_export_excel(self):
        """Génère un fichier Excel et propose le téléchargement."""
        self.ensure_one()
        import xlsxwriter  # disponible dans Odoo

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Variation Stock')

        # ── Formats ──────────────────────────────────────────────────────────
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 13, 'align': 'center', 'valign': 'vcenter',
        })
        label_fmt = workbook.add_format({'bold': True})
        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#1F497D', 'font_color': 'white',
            'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True,
        })
        qty_fmt = workbook.add_format({'num_format': '#,##0.000', 'align': 'right'})
        cost_fmt = workbook.add_format({'num_format': '#,##0.0000', 'align': 'right'})
        money_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        total_qty_fmt = workbook.add_format({
            'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'top': 2,
        })
        total_money_fmt = workbook.add_format({
            'bold': True, 'num_format': '#,##0.00', 'align': 'right', 'top': 2,
        })
        total_label_fmt = workbook.add_format({'bold': True, 'top': 2})
        cost_origin_fmt = workbook.add_format({'align': 'left'})

        # ── En-tête du document ───────────────────────────────────────────────
        num_cols = 7
        ws.merge_range(0, 0, 0, num_cols - 1,
                       'Analyse de variation de stock', title_fmt)
        ws.set_row(0, 24)
        ws.write(1, 0, 'Société :', label_fmt)
        ws.write(1, 1, self.company_id.name)
        ws.write(2, 0, 'Date de début :', label_fmt)
        ws.write(2, 1, str(self.date_from))
        ws.write(3, 0, 'Date de fin :', label_fmt)
        ws.write(3, 1, str(self.date_to))

        # Ligne optionnelle codes analytiques
        if self.analytic_account_ids:
            analytic_names = ', '.join(self.analytic_account_ids.mapped('name'))
            ws.write(4, 0, 'Codes analytiques :', label_fmt)
            ws.merge_range(4, 1, 4, num_cols - 1, analytic_names)
            header_row = 6
        else:
            header_row = 5

        # ── En-têtes colonnes ─────────────────────────────────────────────────
        headers = [
            'Référence', 'Article',
            'Qté achetée', 'Qté vendue',
            'Coût unitaire (achat)', 'Origine du coût',
            'Variation de stock calculée',
        ]
        col_widths = [16, 36, 14, 14, 18, 20, 22]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            ws.write(header_row, col, h, header_fmt)
            ws.set_column(col, col, w)
        ws.set_row(header_row, 30)

        # ── Données ───────────────────────────────────────────────────────────
        row = header_row + 1
        tot = {f: 0.0 for f in ['qty_purchased', 'qty_sold', 'stock_variation']}
        for line in self.line_ids:
            ws.write(row, 0, line.product_code or '')
            ws.write(row, 1, line.product_id.name or '')
            ws.write_number(row, 2, line.qty_purchased, qty_fmt)
            ws.write_number(row, 3, line.qty_sold, qty_fmt)
            ws.write_number(row, 4, line.cost_unit, cost_fmt)
            ws.write(
                row, 5,
                'Fiche article' if line.cost_from_product else 'Achat de la période',
                cost_origin_fmt,
            )
            ws.write_number(row, 6, line.stock_variation, money_fmt)
            for f in tot:
                tot[f] += getattr(line, f)
            row += 1

        # ── Ligne de totaux ───────────────────────────────────────────────────
        ws.write(row, 0, 'TOTAL', total_label_fmt)
        ws.write(row, 1, '', total_label_fmt)
        ws.write_number(row, 2, tot['qty_purchased'], total_qty_fmt)
        ws.write_number(row, 3, tot['qty_sold'], total_qty_fmt)
        ws.write(row, 4, '', total_label_fmt)
        ws.write(row, 5, '', total_label_fmt)
        ws.write_number(row, 6, tot['stock_variation'], total_money_fmt)

        workbook.close()
        output.seek(0)

        filename = 'variation_stock_%s_%s.xlsx' % (self.date_from, self.date_to)
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(output.read()),
            'type': 'binary',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }


class AccountStockVariationLine(models.TransientModel):
    _name = 'account.stock.variation.line'
    _description = "Ligne d'analyse de variation de stock"

    wizard_id = fields.Many2one(
        'account.stock.variation.wizard', ondelete='cascade')
    currency_id = fields.Many2one(
        related='wizard_id.company_id.currency_id', readonly=True)

    product_id = fields.Many2one(
        'product.product', string="Article", readonly=True)
    product_code = fields.Char(
        related='product_id.default_code', string="Référence", readonly=True)

    qty_purchased = fields.Float(
        string="Quantité achetée", readonly=True, digits='Product Unit of Measure')
    qty_sold = fields.Float(
        string="Quantité vendue", readonly=True, digits='Product Unit of Measure')
    cost_unit = fields.Float(
        string="Coût unitaire (achat)", readonly=True, digits='Product Price')
    cost_from_product = fields.Boolean(
        string="Coût issu de la fiche article", readonly=True,
        help="Coché si le coût unitaire n'a pas pu être déterminé à partir d'un achat sur "
             "la période : il provient alors directement du coût de la fiche article.")
    stock_variation = fields.Monetary(
        string="Variation de stock calculée", readonly=True,
        help="(Quantité achetée - Quantité vendue) * Coût unitaire")

    # -------------------------------------------------------------------------
    # Actions : navigation
    # -------------------------------------------------------------------------

    def action_open_product(self):
        """Ouvre la fiche article dans une fenêtre modale."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _action_view_move_lines(self, move_types, title_suffix=''):
        self.ensure_one()
        domain = self.wizard_id._get_base_domain() + [
            ('product_id', '=', self.product_id.id),
            ('move_id.move_type', 'in', move_types),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': '%s%s' % (self.product_id.display_name, title_suffix),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'new',
        }

    def action_view_purchase_lines(self):
        """Lignes de facture / avoir fournisseur ayant servi au calcul."""
        return self._action_view_move_lines(
            ('in_invoice', 'in_refund'), _(' — Achats de la période'))

    def action_view_sale_lines(self):
        """Lignes de facture / avoir client ayant servi au calcul."""
        return self._action_view_move_lines(
            ('out_invoice', 'out_refund'), _(' — Ventes de la période'))
