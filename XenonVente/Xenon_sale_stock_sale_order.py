# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

#MV15
import json
from datetime import datetime, timedelta
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class XenonSaleOrder(models.Model):
    _inherit = "sale.order"
    
    def _action_dempx(self):
        _logger.info('logLLO_action_dempx_6')
        self.order_line._action_launch_stock_rule()
        _logger.info('logLLO_action_dempx_7')
        return super(XenonSaleOrder, self)._action_dempx()
    
class XenonSaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_website_id = fields.Many2one(related='order_id.website_id', store=True, copy=False, string='Website')
    
    @api.depends('product_type', 'product_uom_qty', 'qty_delivered', 'state', 'move_ids', 'product_uom')
    def _compute_qty_to_deliver(self):
        """Compute the visibility of the inventory widget."""
        for line in self:
            line.qty_to_deliver = line.product_uom_qty - line.qty_delivered
            if line.state in ('draft', 'sent', 'sale') and line.product_type == 'product' and line.product_uom and line.qty_to_deliver > 0 and line.x_website_id.id==1:
                _logger.info('logLLO_venteweb')
                if line.state == 'sale' and not line.move_ids:
                    line.display_qty_widget = False
                else:
                    line.display_qty_widget = True
            elif line.state == 'wait' and line.product_type == 'product' and line.product_uom and line.qty_to_deliver > 0:
                _logger.info('logLLO_venteprog')
                line.display_qty_widget = True
            else:
                line.display_qty_widget = False
    
    
    @api.model_create_multi
    def create(self, vals_list):
        lines = super(XenonSaleOrderLine, self).create(vals_list)
        if lines.x_website_id.id == 1:
            _logger.info('logLLO_venteweb2')
            lines.filtered(lambda line: line.state =='sale')._action_launch_stock_rule()
        else:
            _logger.info('logLLO_venteprog2')
            lines.filtered(lambda line: line.state =='wait')._action_launch_stock_rule()
        return lines

    def write(self, values):
        lines = self.env['sale.order.line']
        if 'product_uom_qty' in values:
            #MV15 precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            lines = self.filtered(
                lambda r: r.state == 'sale' and not r.is_expense) #MV15  and float_compare(r.product_uom_qty, values['product_uom_qty'], precision_digits=precision) == -1)
        previous_product_uom_qty = {line.id: line.product_uom_qty for line in lines}
        res = super(XenonSaleOrderLine, self).write(values)
        if lines:
            lines._action_launch_stock_rule(previous_product_uom_qty)
        #MV15
        if 'customer_lead' in values and self.state == 'sale' and not self.order_id.commitment_date:
            # Propagate deadline on related stock move
            self.move_ids.date_deadline = self.order_id.date_order + timedelta(days=self.customer_lead or 0.0)
        return res
    
    
    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        _logger.info('logLLO_action_dempx_8')
        #######################################################pas de demande de prix à cause de ce bloc !!!!!#####################################
        #if self._context.get("skip_procurement"):
        #    _logger.info('logLLO_action_dempx_9')
        #    return True
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        procurements = []
        for line in self:
            _logger.info('logLLO_action_dempx_10' + str(line))
            line = line.with_company(line.company_id)
            if line.x_website_id.id == 1:
                if line.state != 'sale' or not line.product_id.type in ('consu','product'):
                    continue
            else:
                if line.state != 'wait' or not line.product_id.type in ('consu','product'):
                    continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            _logger.info('logLLO_action_dempx_6b' + str(qty))
            if float_compare(qty, line.product_uom_qty, precision_digits=precision) == 0:
                continue

            group_id = line._get_procurement_group()
            _logger.info('logLLO_action_dempx_6c' + str(group_id))
            if not group_id:
                group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                line.order_id.procurement_group_id = group_id
                _logger.info('logLLO_action_dempx_6d' + str(group_id))
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({'move_type': line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty
            
            _logger.info('logLLO_action_dempx_6e' + str(product_qty))

            line_uom = line.product_uom
            quant_uom = line.product_id.uom_id
            product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
            procurements.append(self.env['procurement.group'].Procurement(
                line.product_id, product_qty, procurement_uom,
                line.order_id.partner_shipping_id.property_stock_customer,
                line.product_id.display_name, line.order_id.name, line.order_id.company_id, values))
            _logger.info('logLLO_action_dempx_6f' + str(procurements))
        if procurements:
            self.env['procurement.group'].run(procurements)

        # This next block is currently needed only because the scheduler trigger is done by picking confirmation rather than stock.move confirmation
        orders = self.mapped('order_id')
        for order in orders:
            pickings_to_confirm = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            if pickings_to_confirm:
                # Trigger the Scheduler for Pickings
                pickings_to_confirm.action_confirm()
        return True
