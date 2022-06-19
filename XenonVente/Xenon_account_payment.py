# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from collections import defaultdict

import logging

_logger = logging.getLogger(__name__)

class XenonAccountPayment(models.Model):
    _inherit='account.payment'
    
    x_acomptefrs = fields.Boolean(string="Acompte fournisseur", default=False, copy=False)
    x_acomptecore = fields.Boolean(string="Acompte core", default=False, copy=False)