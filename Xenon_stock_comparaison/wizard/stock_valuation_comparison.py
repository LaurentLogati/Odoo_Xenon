# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime, date as date_cls
from odoo import api, fields, models
from odoo.exceptions import UserError


class StockValuationComparisonWizard(models.TransientModel):
    _name = 'stock.valuation.comparison.wizard'
    _description = "Comparaison de valorisation de stock entre 2 dates"

    date_from = fields.Date(string="Date 1", required=False)
    date_to = fields.Date(string="Date 2", required=False)
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, required=True)
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        string="Codes analytiques",
        help="Si renseigné, seuls les produits dont les mouvements de stock sont "
             "liés à AU MOINS UN de ces codes (vente, achat, facture) apparaissent dans les résultats.",
    )
    line_ids = fields.One2many(
        'stock.valuation.comparison.line', 'wizard_id', string="Résultat")

    def _get_effective_dates(self):
        """Retourne (date_from, date_to) en appliquant des valeurs par défaut si non renseignées.
        - date_from absente → 1900-01-01 (= depuis le début des temps)
        - date_to absente   → date du jour
        """
        date_from = self.date_from or date_cls(1900, 1, 1)
        date_to = self.date_to or fields.Date.today()
        return date_from, date_to

    def _analytic_product_filter_sql(self):
        """Retourne un fragment SQL (et ses params) pour filtrer les produits
        dont les mouvements sont liés à AU MOINS UN des codes analytiques sélectionnés.

        Stratégie OU : pour chaque code analytique, on collecte les product_id
        concernés (via commande vente, commande achat ou facture), puis on
        fait l'union — tout produit lié à au moins un des codes passe le filtre.

        Retourne (sql_fragment, params) où sql_fragment est soit une chaîne
        vide (pas de filtre) soit " AND svl.product_id IN (...) ".
        """
        analytic_ids = self.analytic_account_ids.ids
        if not analytic_ids:
            return '', {}

        # Pour chaque compte analytique, sous-requête des product_id liés
        # (union des 3 sources : vente, achat, facture)
        subqueries = []
        params = {}
        for idx, analytic_id in enumerate(analytic_ids):
            key = 'analytic_%d' % idx
            params[key] = str(analytic_id)
            subqueries.append("""
                SELECT DISTINCT sm2.product_id
                FROM stock_move sm2
                LEFT JOIN sale_order_line sol
                       ON sol.id = sm2.sale_line_id
                LEFT JOIN purchase_order_line pol
                       ON pol.id = sm2.purchase_line_id
                WHERE (
                    (sol.analytic_distribution IS NOT NULL
                        AND sol.analytic_distribution::jsonb ? %%(%s)s)
                    OR
                    (pol.analytic_distribution IS NOT NULL
                        AND pol.analytic_distribution::jsonb ? %%(%s)s)
                )
                UNION
                SELECT DISTINCT svl2.product_id
                FROM stock_valuation_layer svl2
                JOIN account_move_line aml
                  ON aml.id = svl2.account_move_line_id
                WHERE aml.analytic_distribution IS NOT NULL
                  AND aml.analytic_distribution::jsonb ? %%(%s)s
            """ % (key, key, key))

        # UNION de toutes les sous-requêtes → produits liés à AU MOINS UN code
        union_sql = ' UNION '.join(subqueries)
        sql_fragment = ' AND svl.product_id IN (%s) ' % union_sql
        return sql_fragment, params

    def action_compute(self):
        """Calcule la comparaison de stock entre date_from et date_to
        pour tous les articles ayant eu de l'activité de valorisation.
        Si des codes analytiques sont sélectionnés, seuls les produits liés
        à TOUS ces codes (vente, achat, facture) sont inclus.
        Les dates sont optionnelles si un filtre analytique est utilisé."""
        self.ensure_one()

        # Validation : sans filtre analytique, les deux dates sont obligatoires
        if not self.analytic_account_ids:
            if not self.date_from or not self.date_to:
                raise UserError(
                    "Veuillez renseigner les deux dates (Date 1 et Date 2), "
                    "ou utiliser un filtre analytique pour vous en affranchir."
                )

        date_from, date_to = self._get_effective_dates()

        self.line_ids.unlink()

        analytic_sql, analytic_params = self._analytic_product_filter_sql()

        query = """
            WITH svl_data AS (
                SELECT
                    svl.product_id   AS product_id,
                    svl.quantity     AS quantity,
                    svl.value        AS value,
                    svl.create_date  AS create_date,
                    sm.id            AS move_id,
                    spl.usage        AS src_usage,
                    dpl.usage        AS dest_usage
                FROM stock_valuation_layer svl
                LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
                LEFT JOIN stock_location spl ON spl.id = sm.location_id
                LEFT JOIN stock_location dpl ON dpl.id = sm.location_dest_id
                WHERE svl.company_id = %(company_id)s
                {analytic_filter}
            )
            SELECT
                product_id,
                COALESCE(SUM(quantity) FILTER (
                    WHERE create_date::date <= %(date1)s), 0)         AS qty_date1,
                COALESCE(SUM(value) FILTER (
                    WHERE create_date::date <= %(date1)s), 0)         AS value_date1,
                COALESCE(SUM(quantity) FILTER (
                    WHERE create_date::date <= %(date2)s), 0)         AS qty_date2,
                COALESCE(SUM(value) FILTER (
                    WHERE create_date::date <= %(date2)s), 0)         AS value_date2,
                COALESCE(SUM(quantity) FILTER (
                    WHERE create_date::date > %(date1)s
                      AND create_date::date <= %(date2)s
                      AND dest_usage = 'internal'
                      AND (src_usage IS NULL OR src_usage NOT IN ('internal', 'inventory'))
                ), 0)                                                  AS qty_in,
                COALESCE(-SUM(quantity) FILTER (
                    WHERE create_date::date > %(date1)s
                      AND create_date::date <= %(date2)s
                      AND src_usage = 'internal'
                      AND (dest_usage IS NULL OR dest_usage NOT IN ('internal', 'inventory'))
                ), 0)                                                  AS qty_out,
                COALESCE(SUM(quantity) FILTER (
                    WHERE create_date::date > %(date1)s
                      AND create_date::date <= %(date2)s
                      AND (src_usage = 'inventory' OR dest_usage = 'inventory' OR move_id IS NULL)
                ), 0)                                                  AS qty_adjustment
            FROM svl_data
            GROUP BY product_id
            HAVING
                COALESCE(SUM(quantity) FILTER (WHERE create_date::date <= %(date1)s), 0) != 0
                OR COALESCE(SUM(quantity) FILTER (WHERE create_date::date <= %(date2)s), 0) != 0
                OR COALESCE(SUM(quantity) FILTER (
                    WHERE create_date::date > %(date1)s
                      AND create_date::date <= %(date2)s), 0) != 0
        """.format(analytic_filter=analytic_sql)

        query_params = {
            'company_id': self.company_id.id,
            'date1': date_from,
            'date2': date_to,
        }
        query_params.update(analytic_params)

        self.env.cr.execute(query, query_params)
        rows = self.env.cr.dictfetchall()

        lines_vals = []
        for row in rows:
            qty1 = row['qty_date1']
            qty2 = row['qty_date2']
            value1 = row['value_date1']
            value2 = row['value_date2']
            qty_in = row['qty_in']
            qty_out = row['qty_out']
            qty_adj = row['qty_adjustment']
            qty_theoretical = qty1 + qty_in - qty_out
            cost1 = value1 / qty1 if qty1 else 0.0
            cost2 = value2 / qty2 if qty2 else 0.0
            lines_vals.append((0, 0, {
                'product_id': row['product_id'],
                'qty_date1': qty1,
                'cost_date1': cost1,
                'value_date1': value1,
                'qty_in': qty_in,
                'qty_out': qty_out,
                'qty_adjustment': qty_adj,
                'qty_theoretical': qty_theoretical,
                'qty_date2': qty2,
                'cost_date2': cost2,
                'value_date2': value2,
                'qty_gap': qty_theoretical - qty2,
            }))

        self.line_ids = lines_vals

        action = self.env['ir.actions.act_window']._for_xml_id(
            'Xenon_stock_comparaison.action_stock_valuation_comparison_wizard')
        action['res_id'] = self.id
        return action

    def action_print_report(self):
        """Génère le rapport PDF."""
        self.ensure_one()
        return self.env.ref(
            'Xenon_stock_comparaison.action_report_stock_valuation_comparison'
        ).report_action(self)

    def action_export_excel(self):
        """Génère un fichier Excel et propose le téléchargement."""
        self.ensure_one()
        import xlsxwriter  # disponible dans Odoo

        date_from, date_to = self._get_effective_dates()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Comparaison Stock')

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
        qty_fmt    = workbook.add_format({'num_format': '#,##0.000', 'align': 'right'})
        cost_fmt   = workbook.add_format({'num_format': '#,##0.0000', 'align': 'right'})
        money_fmt  = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        gap_fmt    = workbook.add_format({
            'num_format': '#,##0.000', 'align': 'right',
            'font_color': 'red', 'bold': True,
        })
        total_qty_fmt = workbook.add_format({
            'bold': True, 'num_format': '#,##0.000',
            'align': 'right', 'top': 2,
        })
        total_money_fmt = workbook.add_format({
            'bold': True, 'num_format': '#,##0.00',
            'align': 'right', 'top': 2,
        })
        total_label_fmt = workbook.add_format({'bold': True, 'top': 2})

        # ── Formats pour lignes négatives (qty_date2 < 0) ────────────────────
        red_text_fmt  = workbook.add_format({'font_color': 'red'})
        red_qty_fmt   = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'font_color': 'red'})
        red_cost_fmt  = workbook.add_format({'num_format': '#,##0.0000', 'align': 'right', 'font_color': 'red'})
        red_money_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'right', 'font_color': 'red'})
        red_gap_fmt   = workbook.add_format({
            'num_format': '#,##0.000', 'align': 'right',
            'font_color': 'red', 'bold': True,
        })

        # ── En-tête du document ───────────────────────────────────────────────
        num_cols = 13
        ws.merge_range(0, 0, 0, num_cols - 1,
                       'Comparaison de valorisation de stock', title_fmt)
        ws.set_row(0, 24)
        ws.write(1, 0, 'Société :', label_fmt)
        ws.write(1, 1, self.company_id.name)
        ws.write(2, 0, 'Date 1 :', label_fmt)
        ws.write(2, 1, str(self.date_from) if self.date_from else str(date_from))
        ws.write(3, 0, 'Date 2 :', label_fmt)
        ws.write(3, 1, str(self.date_to) if self.date_to else str(date_to))

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
            'Qté date 1', 'Coût U. date 1', 'Valeur date 1',
            'Qté reçue', 'Qté livrée', 'Qté théorique',
            'Qté date 2', 'Coût U. date 2', 'Valeur date 2',
            'Écart qté', 'Ajust. inventaire',
        ]
        col_widths = [16, 32, 12, 14, 16, 12, 12, 14, 12, 14, 16, 12, 16]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            ws.write(header_row, col, h, header_fmt)
            ws.set_column(col, col, w)
        ws.set_row(header_row, 30)

        # ── Données ───────────────────────────────────────────────────────────
        row = header_row + 1
        tot = {f: 0.0 for f in [
            'qty_date1', 'value_date1', 'qty_in', 'qty_out',
            'qty_theoretical', 'qty_date2', 'value_date2',
            'qty_gap', 'qty_adjustment',
        ]}
        for line in self.line_ids:
            is_red = line.qty_date2 < 0
            f_text  = red_text_fmt  if is_red else None
            f_qty   = red_qty_fmt   if is_red else qty_fmt
            f_cost  = red_cost_fmt  if is_red else cost_fmt
            f_money = red_money_fmt if is_red else money_fmt
            f_gap   = red_gap_fmt   if is_red or line.qty_gap != 0 else qty_fmt

            ws.write(row, 0, line.product_code or '', f_text)
            ws.write(row, 1, line.product_id.name or '', f_text)
            ws.write_number(row, 2, line.qty_date1, f_qty)
            ws.write_number(row, 3, line.cost_date1, f_cost)
            ws.write_number(row, 4, line.value_date1, f_money)
            ws.write_number(row, 5, line.qty_in, f_qty)
            ws.write_number(row, 6, line.qty_out, f_qty)
            ws.write_number(row, 7, line.qty_theoretical, f_qty)
            ws.write_number(row, 8, line.qty_date2, f_qty)
            ws.write_number(row, 9, line.cost_date2, f_cost)
            ws.write_number(row, 10, line.value_date2, f_money)
            ws.write_number(row, 11, line.qty_gap, f_gap)
            ws.write_number(row, 12, line.qty_adjustment, f_qty)
            for f in tot:
                tot[f] += getattr(line, f)
            row += 1

        # ── Ligne de totaux ───────────────────────────────────────────────────
        ws.write(row, 0, 'TOTAL', total_label_fmt)
        ws.write(row, 1, '', total_label_fmt)
        ws.write_number(row, 2, tot['qty_date1'], total_qty_fmt)
        ws.write(row, 3, '', total_label_fmt)
        ws.write_number(row, 4, tot['value_date1'], total_money_fmt)
        ws.write_number(row, 5, tot['qty_in'], total_qty_fmt)
        ws.write_number(row, 6, tot['qty_out'], total_qty_fmt)
        ws.write_number(row, 7, tot['qty_theoretical'], total_qty_fmt)
        ws.write_number(row, 8, tot['qty_date2'], total_qty_fmt)
        ws.write(row, 9, '', total_label_fmt)
        ws.write_number(row, 10, tot['value_date2'], total_money_fmt)
        ws.write_number(row, 11, tot['qty_gap'], total_qty_fmt)
        ws.write_number(row, 12, tot['qty_adjustment'], total_qty_fmt)

        workbook.close()
        output.seek(0)

        date_from_str = str(self.date_from) if self.date_from else str(date_from)
        date_to_str = str(self.date_to) if self.date_to else str(date_to)
        filename = 'comparaison_stock_%s_%s.xlsx' % (date_from_str, date_to_str)
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


class StockValuationComparisonLine(models.TransientModel):
    _name = 'stock.valuation.comparison.line'
    _description = "Ligne de comparaison de valorisation de stock"

    wizard_id = fields.Many2one(
        'stock.valuation.comparison.wizard', ondelete='cascade')
    currency_id = fields.Many2one(
        related='wizard_id.company_id.currency_id', readonly=True)

    product_id = fields.Many2one(
        'product.product', string="Article", readonly=True)
    product_code = fields.Char(
        related='product_id.default_code', string="Référence", readonly=True)

    qty_date1 = fields.Float(string="Qté date 1", readonly=True, digits='Product Unit of Measure')
    cost_date1 = fields.Float(string="Coût unitaire date 1", readonly=True, digits='Product Price')
    value_date1 = fields.Monetary(string="Valorisation date 1", readonly=True)

    qty_in = fields.Float(string="Qté réceptionnée", readonly=True, digits='Product Unit of Measure')
    qty_out = fields.Float(string="Qté livrée", readonly=True, digits='Product Unit of Measure')
    qty_adjustment = fields.Float(string="Qté ajust. inventaire", readonly=True, digits='Product Unit of Measure')
    qty_theoretical = fields.Float(string="Qté théorique", readonly=True, digits='Product Unit of Measure')

    qty_date2 = fields.Float(string="Qté date 2", readonly=True, digits='Product Unit of Measure')
    cost_date2 = fields.Float(string="Coût unitaire date 2", readonly=True, digits='Product Price')
    value_date2 = fields.Monetary(string="Valorisation date 2", readonly=True)

    qty_gap = fields.Float(string="Écart quantité", readonly=True, digits='Product Unit of Measure')

    # -------------------------------------------------------------------------
    # Actions : navigation article
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

    # -------------------------------------------------------------------------
    # Actions : détail des mouvements de valorisation
    # -------------------------------------------------------------------------

    def _action_view_svl(self, extra_domain, title_suffix=''):
        """Ouvre les couches de valorisation filtrées dans une fenêtre modale."""
        self.ensure_one()
        domain = [
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.wizard_id.company_id.id),
        ] + extra_domain
        return {
            'type': 'ir.actions.act_window',
            'name': '%s%s' % (self.product_id.display_name, title_suffix),
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'new',
        }

    def _end_of_day(self, d):
        """Retourne un datetime à 23:59:59 pour la date donnée."""
        return datetime(d.year, d.month, d.day, 23, 59, 59)

    def action_view_svl_date1(self):
        """Couches de valorisation cumulées au date 1."""
        self.ensure_one()
        d1, _d2 = self.wizard_id._get_effective_dates()
        return self._action_view_svl(
            [('create_date', '<=', self._end_of_day(d1))],
            ' — Stock au %s' % fields.Date.to_string(d1),
        )

    def action_view_svl_period(self):
        """Couches de valorisation entre date 1 et date 2."""
        self.ensure_one()
        d1, d2 = self.wizard_id._get_effective_dates()
        return self._action_view_svl(
            [
                ('create_date', '>', self._end_of_day(d1)),
                ('create_date', '<=', self._end_of_day(d2)),
            ],
            ' — Mvts du %s au %s' % (fields.Date.to_string(d1), fields.Date.to_string(d2)),
        )

    def action_view_svl_date2(self):
        """Couches de valorisation cumulées au date 2."""
        self.ensure_one()
        _d1, d2 = self.wizard_id._get_effective_dates()
        return self._action_view_svl(
            [('create_date', '<=', self._end_of_day(d2))],
            ' — Stock au %s' % fields.Date.to_string(d2),
        )

    def action_view_svl_adjustment(self):
        """Ajustements d'inventaire (mouvements depuis/vers emplacement inventaire) sur la période."""
        self.ensure_one()
        d1, d2 = self.wizard_id._get_effective_dates()
        dt1 = self._end_of_day(d1)
        dt2 = self._end_of_day(d2)
        domain = [
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.wizard_id.company_id.id),
            ('create_date', '>', dt1),
            ('create_date', '<=', dt2),
            '|', '|',
            ('stock_move_id', '=', False),
            ('stock_move_id.location_id.usage', '=', 'inventory'),
            ('stock_move_id.location_dest_id.usage', '=', 'inventory'),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': '%s — Ajustements inventaire' % self.product_id.display_name,
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'new',
        }
