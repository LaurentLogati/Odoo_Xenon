import json
import logging

from collections import defaultdict
from datetime import timedelta
from itertools import groupby

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import (
    AccessError,
    RedirectWarning,
    UserError,
    ValidationError,
)
from odoo.fields import Command
from odoo.http import request
from odoo.osv import expression
from odoo.tools import (
    create_index,
    float_is_zero,
    format_amount,
    format_date,
    is_html_empty,
    SQL,
)
from odoo.tools.mail import html_keep_url

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)

INVOICE_STATUS = [
    ('upselling', 'Upselling Opportunity'),
    ('invoiced', 'Fully Invoiced'),
    ('to invoice', 'To Invoice'),
    ('no', 'Nothing to Invoice')
]

SALE_ORDER_STATE = [
    ('draft', "Quotation"),
    ('wait', 'Attente px'),
    ('tosend', 'A envoyer'),
    ('sent', "Quotation Sent"),
    ('sale', "Sales Order"),
    ('cancel', "Cancelled"),
]



class XenonSaleOrder(models.Model):
    _inherit='sale.order'

    state = fields.Selection([
       ('draft', 'Quotation'),
        ('wait', 'Attente px'),
        ('tosend', 'A envoyer'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        #('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    
    #x_mto_done=fields.Boolean(string="mto fait", default=False, copy=False)
    
    x_amount_filtre = fields.Monetary(string='Total_filtre', store=True, compute='_amount_filtre', tracking=4)
    
    def _action_dempx(self):
        """ Implementation of additionnal mecanism of Sales Order confirmation.
            This method should be extended when the confirmation should generated
            other documents. In this method, the SO are in 'sale' state (not yet 'done').
        """
        # create an analytic account if at least an expense product
        _logger.info('logLLO18_action_dempx_1')
        #for order in self:
        #    if any([expense_policy not in [False, 'no'] for expense_policy in order.order_line.mapped('product_id.expense_policy')]):
        #        if not order.analytic_account_id:
        #            order._create_analytic_account()
        ##return True
        ## recherche des articles ayant fait l'objet d'une demande de prix (demande de prix non annulée MEP_01.4)
        ## les lignes d'articles qui n'auront pas fait l'objet de demande de prix seront mises à jour avec le flag de majpx à true
        for order in self:
            commandefrs = self.env['purchase.order'].search([('origin', '=', order.name),('state', '!=', 'cancel')])
            list_art=[]
            for cde in commandefrs:
                artcde=cde.env['purchase.order.line'].search([('order_id', '=', cde.id)])
                for art in artcde:
                    list_art.append(art.product_id.id)
                    #commande.env['sale.order.line'].search([('order_id','=',commande.id)])
        order.order_line.sudo()._maj_ligne_sans_dem_px(list_art)
        nbligne_x_px_maj=self.env['sale.order.line'].search_count([('order_id', '=', self.id),('x_px_maj', '!=', 't'), ('display_type', '!=', 'line_section')])
        if nbligne_x_px_maj==0:
            self.write({
            'state': 'tosend',
            'date_order': fields.Datetime.now(),
            })
        if not list_art:
            self.write({
            'state': 'tosend',
            'date_order': fields.Datetime.now(),
            })
        return True

 
    def action_dempx(self):
        _logger.info('logLLO18_action_dempx_2')
        #if self._get_forbidden_state_confirm() & set(self.mapped('state')):
        #    raise UserError(_(
        #        'It is not allowed to confirm an order in the following states: %s'
        #    ) % (', '.join(self._get_forbidden_state_confirm())))

        #for order in self.filtered(lambda order: order.partner_id not in order.message_partner_ids):
        #    order.message_subscribe([order.partner_id.id])

        for order in self:
            error_msg = order._confirmation_error_message()
            if error_msg:
                raise UserError(error_msg)

        self.order_line._validate_analytic_distribution()

        for order in self:
            if order.partner_id in order.message_partner_ids:
                continue
            order.message_subscribe([order.partner_id.id])

        self.write(self._prepare_confirmation_values())

        #for order in self:
        #    if order.partner_id in order.message_partner_ids:
        #        continue
        #    order.message_subscribe([order.partner_id.id])
        #    
        #self.write({
        #    'state': 'wait',
        #    'date_order': fields.Datetime.now(),
        #})
        #'x_mto_done':True              ############################
        
        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)
        context.pop('default_user_id', None)

        #self.with_context(context)._action_confirm()
        self.with_context(context)._action_dempx()
        #if self.env.user.has_group('sale.group_auto_done_setting'):
        #    self.action_done()
        self.filtered(lambda so: so._should_be_locked()).action_lock()

        if self.env.context.get('send_email'):
            self._send_order_confirmation_mail()
            
        return True

    def _prepare_confirmation_values(self):
        """ Prepare the sales order confirmation values.

        Note: self can contain multiple records.

        :return: Sales Order confirmation values
        :rtype: dict
        """
        _logger.info('logLLO18_prepare_confirmation_values')
        return {
            'state': 'wait',
            'date_order': fields.Datetime.now()
        }

    def _get_forbidden_state_confirm(self):
        return {'done', 'cancel'}
    
    def action_majstatut(self):
        # Modification du statut de la commande frs liée############################## utilisée lors de la validation du devis sur le portail web
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name), ('company_id','=', self.company_id.id)])
        cdefrs.update({'state':'tosend'})
        #Ajout du code analytique du devis client sur les lignes du devis frs ### MEP_07.1
        for ligne in cdefrs.order_line:
            #ligne.update({'account_analytic_id':self.analytic_account_id})
            # Chercher la ligne de vente correspondante (si elle existe)
            sale_line = self.order_line.filtered(lambda l: l.product_id == ligne.product_id)
            if sale_line and sale_line[0].analytic_distribution:
                ligne.update({'analytic_distribution': sale_line[0].analytic_distribution})
    

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_so_as_sent'):
            self.filtered(lambda o: o.state == 'tosend').with_context(tracking_disable=True).write({'state': 'sent'})
        so_ctx = {'mail_post_autofollow': self.env.context.get('mail_post_autofollow', True)}
        if self.env.context.get('mark_so_as_sent') and 'mail_notify_author' not in kwargs:
            kwargs['notify_author'] = self.env.user.partner_id.id in (kwargs.get('partner_ids') or [])
        return super(XenonSaleOrder, self.with_context(**so_ctx)).message_post(**kwargs)

    

    def _action_confirmx(self):
        """ Implementation of additional mechanism of Sales Order confirmation.
            This method should be extended when the confirmation should generated
            other documents. In this method, the SO are in 'sale' state (not yet 'done').
        """
        pass
    
    def action_confirmx(self):
        if self._get_forbidden_state_confirm() & set(self.mapped('state')):
            raise UserError(_(
                'It is not allowed to confirm an order in the following states: %s'
            ) % (', '.join(self._get_forbidden_state_confirm())))

        for order in self.filtered(lambda order: order.partner_id not in order.message_partner_ids):
            order.message_subscribe([order.partner_id.id])
        self.write({
            'state': 'sale',
            'date_order': fields.Datetime.now()
        })
        # Modification du statut de la commande frs liée - on ne met à jour que les commandes non annulées ##############################LLO
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name), ('state', '!=', 'cancel'), ('company_id','=', self.company_id.id)])             
        cdefrs.update({'state':'tosend'})
        
        #Ajout du code analytique du devis client sur les lignes du devis frs ### MEP_07.1
        for ligne in cdefrs.order_line:
            # Chercher la ligne de vente correspondante (si elle existe)
            sale_line = self.order_line.filtered(lambda l: l.product_id == ligne.product_id)
            if sale_line and sale_line[0].analytic_distribution:
                ligne.update({'analytic_distribution': sale_line[0].analytic_distribution})
        
        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)
        self.with_context(context)._action_confirmx()
        if self.env.user.has_group('sale.group_auto_done_setting'):#pas de passage
            self.action_done()
        return True
    
    def action_aenvoyerx(self):
        #possibilité pour les comptables/advisor de forcer le devis en statut à envoyer
        self.write({
            'state': 'tosend',
        })
    
    def action_confirmersansmailx(self):
        #possibilité pour les comptables/advisor de forcer le devis en statut confirmer sans envoyer de mail
        self.write({
            'state': 'sale',
        })
        # Modification du statut de la commande frs liée - on ne met à jour que les commandes non annulées ##############################LLO
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name), ('state', '!=', 'cancel'), ('company_id','=', self.company_id.id)])             
        cdefrs.update({'state':'tosend'})
        #Ajout du code analytique du devis client sur les lignes du devis frs ### MEP_07.1
        for ligne in cdefrs.order_line:
            #ligne.update({'account_analytic_id':self.analytic_account_id})
            # Chercher la ligne de vente correspondante (si elle existe)
            sale_line = self.order_line.filtered(lambda l: l.product_id == ligne.product_id)
            if sale_line and sale_line[0].analytic_distribution:
                ligne.update({'analytic_distribution': sale_line[0].analytic_distribution})
    
    @api.depends('order_line.price_subtotal')
    def _amount_filtre(self):
        """
        Compute the total amounts of the SO si le type d'article est produit ou le groupe d'article est sous-traitance.
        """
        for order in self:
            x_amount_filtre = 0.0
            for line in order.order_line:
                if line.product_template_id.type=='product' or line.product_template_id.categ_id.x_filtre==True:
                    x_amount_filtre += line.price_subtotal
            order.update({
                'x_amount_filtre': x_amount_filtre,
            })

    @api.onchange('custom_state')
    def _onchange_custom_state(self):
        # Forcer le recalcul des mouvements liés
        self.order_line.mapped('move_ids')._compute_forecast_information()
        
    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            sequence = 1
            def sort_key(line):
                # Prendre le premier SO lié, sinon chaîne vide
                order_name = line.sale_line_ids.order_id[:1].name or 'zzz'
                return (order_name, line.sequence)

            lines_sorted = move.invoice_line_ids.sorted(key=sort_key)
            for line in lines_sorted:
                line.write({'sequence': sequence})
                sequence += 1
        return moves
        
      
class XenonSaleOrderLine(models.Model):
    _inherit= 'sale.order.line'
    
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('wait', 'Attente px'),
        ('tosend', 'A envoyer'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], related='order_id.state', string='Order Status', readonly=True, copy=False, store=True, default='draft')
    
    x_px_maj = fields.Boolean(string="prix mis à jour", default=False, copy=False)
    
    
    def _maj_ligne_sans_dem_px(self,list_art):
        for line in self:
            if line.product_id.id not in list_art:
                if line.product_id.type!='service':         #MEP_01.5
                    prixvente=self.env['product.template'].search([('id','=',line.product_id.product_tmpl_id.id)]).list_price
                    line.update({'price_unit':prixvente,'x_px_maj':True})
                else:                                       #MEP_01.5.1
                    line.update({'x_px_maj':True})
                



               

    
    
    
