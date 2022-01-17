# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import binascii
from datetime import date

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.osv import expression

from odoo.addons.sale.controllers.portal import CustomerPortal

import logging

_logger = logging.getLogger(__name__)

#remplace odoo\addons\sale\controllers\portal.py
class XenonCustomerPortal(CustomerPortal):

    @http.route(['/my/orders/<int:order_id>/accept'], type='json', auth="public", website=True)
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        # get from query string if not on json param
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid order.')}

        if not order_sudo.has_to_be_signed():
            return {'error': _('The order is not in a state requiring customer signature.')}
        if not signature:
            return {'error': _('Signature is missing.')}

        try:
            order_sudo.write({
                'signed_by': name,
                'signed_on': fields.Datetime.now(),
                'signature': signature,
            })
            request.env.cr.commit()
        except (TypeError, binascii.Error) as e:
            return {'error': _('Invalid signature data.')}

        if not order_sudo.has_to_be_paid():
            order_sudo.action_confirm()
            order_sudo._send_order_confirmation_mail()
            order_sudo.action_majstatut()

        pdf = request.env.ref('sale.action_report_saleorder').sudo().render_qweb_pdf([order_sudo.id])[0]

        _message_post_helper(
            'sale.order', order_sudo.id, _('Order signed by %s') % (name,),
            attachments=[('%s.pdf' % order_sudo.name, pdf)],
            **({'token': access_token} if access_token else {}))

        query_string = '&message=sign_ok'
        if order_sudo.has_to_be_paid(True):
            query_string += '#allow_payment=yes'
        return {
            'force_refresh': True,
            'redirect_url': order_sudo.get_portal_url(query_string=query_string),
        }
