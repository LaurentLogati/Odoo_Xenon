from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('start_date')
    def _onchange_start_date_oca(self):
        """Synchronise start_date (OCA) -> deferred_start_date (standard v18)"""
        if self.start_date and self.start_date != self.deferred_start_date:
            self.deferred_start_date = self.start_date
        elif not self.start_date:
            self.deferred_start_date = False

    @api.onchange('end_date')
    def _onchange_end_date_oca(self):
        """Synchronise end_date (OCA) -> deferred_end_date (standard v18)"""
        if self.end_date and self.end_date != self.deferred_end_date:
            self.deferred_end_date = self.end_date
        elif not self.end_date:
            self.deferred_end_date = False

    @api.onchange('deferred_start_date')
    def _onchange_deferred_start_date(self):
        """Synchronise deferred_start_date (standard v18) -> start_date (OCA)"""
        if self.deferred_start_date and self.deferred_start_date != self.start_date:
            self.start_date = self.deferred_start_date
        elif not self.deferred_start_date:
            self.start_date = False

    @api.onchange('deferred_end_date')
    def _onchange_deferred_end_date(self):
        """Synchronise deferred_end_date (standard v18) -> end_date (OCA)"""
        if self.deferred_end_date and self.deferred_end_date != self.end_date:
            self.end_date = self.deferred_end_date
        elif not self.deferred_end_date:
            self.end_date = False
