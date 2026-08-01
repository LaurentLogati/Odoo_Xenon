# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockValuationComparisonWizard(models.TransientModel):
    _name = 'stock.valuation.comparison.wizard'
    _description = "Comparaison de valorisation de stock entre 2 dates"

    date_from = fields.Date(string="Date 1", required=True)
    date_to = fields.Date(string="Date 2", required=True)
    company_id = fields.Many2one(
        'res.company', string="Société",
        default=lambda self: self.env.company, required=True)
    line_ids = fields.One2many(
        'stock.valuation.comparison.line', 'wizard_id', string="Résultat")

    def action_compute(self):
        """Calcule la comparaison de stock entre date_from et date_to
        pour tous les articles ayant eu de l'activité de valorisation."""
        self.ensure_one()
        self.line_ids.unlink()

        self.env.cr.execute("""
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
        """, {
            'company_id': self.company_id.id,
            'date1': self.date_from,
            'date2': self.date_to,
        })
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
            qty_theoretical = qty1 + qty_in - qty_out + qty_adj
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
