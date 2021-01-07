# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare
from dateutil import relativedelta
from odoo.exceptions import UserError

from odoo.addons.purchase.models.purchase import PurchaseOrder as Purchase


class XenonPurchaseOrder(models.Model):
    _inherit = 'purchase.order'


    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def button_approve(self, force=False):
        result = super(XenonPurchaseOrder, self).button_approve(force=force)
        self._create_picking()
        return result
