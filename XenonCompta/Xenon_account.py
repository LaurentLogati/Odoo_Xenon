# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, tools
from odoo.osv import expression
from odoo.exceptions import UserError, ValidationError


class XenonAccountAccount(models.Model):
    _inherit = 'account.account'

    x_group_id = fields.Many2one('account.group')
