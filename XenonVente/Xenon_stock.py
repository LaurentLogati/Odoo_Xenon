# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from psycopg2 import Error, OperationalError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class XenonStockQuant(models.Model):
    _inherit = "stock.quant"
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=lambda self: self._domain_product_id(),
        ondelete='restrict', required=True, index=True, check_company=True)
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product Template',
        related='product_id.product_tmpl_id')
    x_emplacement= fields.Many2one(related='product_tmpl_id.x_emplacement') #OK MAIS PAS DE GROUP BY !!!
    x_emplacement2= fields.Many2one(related='product_tmpl_id.x_emplacement2') #OK MAIS PAS DE GROUP BY !!!