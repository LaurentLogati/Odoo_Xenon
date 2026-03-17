# -*- coding: utf-8 -*-
import binascii
from odoo import fields, http, SUPERUSER_ID, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.sale.controllers.portal import CustomerPortal
import logging
_logger = logging.getLogger(__name__)

class XenonCustomerPortal(CustomerPortal):

    @http.route(['/my/orders/<int:order_id>/accept'], type='json', auth="public", website=True)
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid order.')}

        # Correction v18 : _has_to_be_signed() avec underscore
        if not order_sudo._has_to_be_signed():
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
        except (TypeError, binascii.Error):
            return {'error': _('Invalid signature data.')}

        # Correction v18 : _has_to_be_paid() avec underscore
        if not order_sudo._has_to_be_paid():
            # Utiliser la méthode custom qui gère tosend et les commandes fournisseurs
            order_sudo.action_confirmx()
            order_sudo._send_order_confirmation_mail()

        # Correction v18 : _render_qweb_pdf remplacé par _render_document_pdf ou _render
        try:
            pdf = request.env.ref('sale.action_report_saleorder').with_user(SUPERUSER_ID)._render_qweb_pdf([order_sudo.id])[0]
        except Exception:
            pdf = None

        # Correction v18 : _message_post_helper supprimé, utiliser message_post directement
        if pdf:
            order_sudo.with_user(SUPERUSER_ID).message_post(
                body=_('Order signed by %s') % name,
                attachments=[('%s.pdf' % order_sudo.name, pdf)],
            )
        else:
            order_sudo.with_user(SUPERUSER_ID).message_post(
                body=_('Order signed by %s') % name,
            )

        query_string = '&message=sign_ok'
        # Correction v18 : _has_to_be_paid() avec underscore
        if order_sudo._has_to_be_paid():
            query_string += '#allow_payment=yes'

        return {
            'force_refresh': True,
            'redirect_url': order_sudo.get_portal_url(query_string=query_string),
        }