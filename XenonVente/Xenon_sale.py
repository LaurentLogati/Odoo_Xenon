from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)

class XenonSaleOrder(models.Model):
    _inherit='sale.order'
  
    state = fields.Selection([
       ('draft', 'Quotation'),
        ('wait', 'Attente px'),
        ('tosend', 'A envoyer'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
    
    #x_mto_done=fields.Boolean(string="mto fait", default=False, copy=False)
    
    def _action_dempx(self):
        """ Implementation of additionnal mecanism of Sales Order confirmation.
            This method should be extended when the confirmation should generated
            other documents. In this method, the SO are in 'sale' state (not yet 'done').
        """
        # create an analytic account if at least an expense product
        for order in self:
            if any([expense_policy not in [False, 'no'] for expense_policy in order.order_line.mapped('product_id.expense_policy')]):
                if not order.analytic_account_id:
                    order._create_analytic_account()
        #return True
        # recherche des articles ayant fait l'objet d'une demande de prix (demande de prix non annulée MEP_01.4)
        # les lignes d'articles qui n'auront pas fait l'objet de demande de prix seront mises à jour avec le flag de majpx à true
        for order in self:
            commandefrs = self.env['purchase.order'].search([('origin', '=', order.name),('state', '!=', 'cancel')])
            list_art=[]
            for cde in commandefrs:
                artcde=cde.env['purchase.order.line'].search([('order_id', '=', cde.id)])
                for art in artcde:
                    list_art.append(art.product_id.id)
                    #commande.env['sale.order.line'].search([('order_id','=',commande.id)])
        order.order_line.sudo()._maj_ligne_sans_dem_px(list_art)
        if not list_art:
            self.write({
            'state': 'tosend',
            'date_order': fields.Datetime.now(),
            })
        return True

 
    def action_dempx(self):
        if self._get_forbidden_state_confirm() & set(self.mapped('state')):
            raise UserError(_(
                'It is not allowed to confirm an order in the following states: %s'
            ) % (', '.join(self._get_forbidden_state_confirm())))

        for order in self.filtered(lambda order: order.partner_id not in order.message_partner_ids):
            order.message_subscribe([order.partner_id.id])
        self.write({
            'state': 'wait',
            'date_order': fields.Datetime.now(),
        })
        #'x_mto_done':True              ############################
        
        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)

        #self.with_context(context)._action_confirm()
        self.with_context(context)._action_dempx()
        if self.env.user.has_group('sale.group_auto_done_setting'):
            self.action_done()
        return True
    
    def action_majstatut(self):
        # Modification du statut de la commande frs liée############################## non utilisée ?
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name)])
        cdefrs.update({'state':'tosend'})
    
    
    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_so_as_sent'):
            self.filtered(lambda o: o.state == 'tosend').with_context(tracking_disable=True).write({'state': 'sent'})
            self.env.company.sudo().set_onboarding_step_done('sale_onboarding_sample_quotation_state')
        return super(XenonSaleOrder, self.with_context(mail_post_autofollow=True)).message_post(**kwargs)

    

    def _action_confirmx(self):
        """ Implementation of additionnal mecanism of Sales Order confirmation.
            This method should be extended when the confirmation should generated
            other documents. In this method, the SO are in 'sale' state (not yet 'done').
        """
        # create an analytic account if at least an expense product
        for order in self:
            if any([expense_policy not in [False, 'no'] for expense_policy in order.order_line.mapped('product_id.expense_policy')]):
                if not order.analytic_account_id:
                    order._create_analytic_account()

        return True
    
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
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name), ('state', '!=', 'cancel')])             
        cdefrs.update({'state':'tosend'})
        
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
        cdefrs=self.env['purchase.order'].search([('origin','=', self.name), ('state', '!=', 'cancel')])             
        cdefrs.update({'state':'tosend'})
      
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
                prixvente=self.env['product.template'].search([('id','=',line.product_id.product_tmpl_id.id)]).list_price
                line.update({'price_unit':prixvente,'x_px_maj':True})
                



               

    
    
    