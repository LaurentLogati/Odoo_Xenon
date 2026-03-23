from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def write(self, vals):
        # Synchronise OCA -> standard v18
        if 'start_date' in vals and 'deferred_start_date' not in vals:
            vals['deferred_start_date'] = vals['start_date']
        if 'end_date' in vals and 'deferred_end_date' not in vals:
            vals['deferred_end_date'] = vals['end_date']
        # Synchronise standard v18 -> OCA
        if 'deferred_start_date' in vals and 'start_date' not in vals:
            vals['start_date'] = vals['deferred_start_date']
        if 'deferred_end_date' in vals and 'end_date' not in vals:
            vals['end_date'] = vals['deferred_end_date']
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Synchronise OCA -> standard v18
            if 'start_date' in vals and 'deferred_start_date' not in vals:
                vals['deferred_start_date'] = vals['start_date']
            if 'end_date' in vals and 'deferred_end_date' not in vals:
                vals['deferred_end_date'] = vals['end_date']
            # Synchronise standard v18 -> OCA
            if 'deferred_start_date' in vals and 'start_date' not in vals:
                vals['start_date'] = vals['deferred_start_date']
            if 'deferred_end_date' in vals and 'end_date' not in vals:
                vals['end_date'] = vals['deferred_end_date']
        return super().create(vals_list)
