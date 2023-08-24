# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)



class XenonProductCategory(models.Model):
    _inherit='product.category'
    
    x_filtre = fields.Boolean(string="filtre", default=False, copy=False)
    
class XenonProductProduct(models.Model): #product template !!!!!!!!
    _inherit = "product.template"

    x_emplacement = fields.Many2one('stock.location', 'Emplacement') #Fly
    x_emplacement2 = fields.Many2one('stock.location', 'Emplacement') #ASA
