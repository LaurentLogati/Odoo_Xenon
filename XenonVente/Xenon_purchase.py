# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, get_lang

import logging

_logger = logging.getLogger(__name__)
       
class XenonPurchaseOrder(models.Model):
    _inherit = 'purchase.order' 
    
    state = fields.Selection([
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('wait', 'Attente client'),
        ('tosend', 'A envoyer'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    
    
    def write(self, vals):
        res = super(XenonPurchaseOrder, self).write(vals)
        
        # MEP_05.1 Suppression des followers/abonnés attachés à un devis pour ne pas leur envoyer de mail lors du changement de frs
        
        #recherche partenaire actuel
        #partnercurrentuser=self.env.user.partner_id
        
        #liste des utilisateurs
        partneruser=self.env['res.users'].search([('login', '!=', 'xyz')]).partner_id #liste des users
        #liste des followers du devis en cours
        followersPCH=self.env['mail.followers'].search([('res_model','=','purchase.order'),('res_id','=',self.id)])

        #liste des followers ne correspondant pas à un utilisateur (pour n'avoir que des fournisseurs)
        followersdevis=followersPCH.partner_id - partneruser
        
        for follower in followersdevis:
            #suppression des followers/abonnés précédents si différent du frs du devis
            if follower.id != self.partner_id.id:
                followersPCH.search([('partner_id', '=', follower.id)]).sudo().unlink()
        # fin MEP_05.1
        
        if vals.get('date_planned'):
            self.order_line.filtered(lambda line: not line.display_type).date_planned = vals['date_planned']
        return res


    def attente_client_confirm(self):
        for order in self:
            
        # 1- Mise à jour de la liste de prix fournisseur
            for line in self.order_line:
                # On ne tient pas compte des lignes de type section ou note
                if line.product_id.display_name != False:
                    # Do not add a contact as a supplier
                    partner = self.partner_id if not self.partner_id.parent_id else self.partner_id.parent_id
                    if line.product_id and partner in line.product_id.seller_ids.mapped('name'):
                        # Convert the price in the right currency.
                        currency = partner.property_purchase_currency_id or self.env.company.currency_id
                        price = self.currency_id._convert(line.price_unit, currency, line.company_id, line.date_order or fields.Date.today(), round=False)
                        if line.product_id.product_tmpl_id.uom_po_id != line.product_uom:
                            default_uom = line.product_id.product_tmpl_id.uom_po_id
                            price = line.product_uom._compute_price(price, default_uom)
                        self.env['product.supplierinfo'].search([('name','=',partner.id),('product_tmpl_id','=',line.product_id.product_tmpl_id.id)]).update({'price': price})
                    else:
                        raise UserError(_(str(partner.name) + " n''est pas associé au produit %s. Veuillez définir ce fournisseur dans la liste des prix des fournisseurs du produit.") % (line.product_id.display_name,))
                        
                                                                    
                                                                                                                                
                                                                      
                                                                  

            # 2- Mise à jour du prix de l'article dans le devis client 
            # le process a été modifié pour avoir une seule demande de prix frs pour un devis client cf Xenon_purchase_stock_rule
            # TODO recherche de la liste pourcentage en fonction des dates
            # TODO mise à jour du prix de vente dans la fiche article

                    rec_liste=self.env['sale.order'].search([('name','=', self.origin)])
                    for commande in rec_liste:
                        lignecommande=commande.env['sale.order.line'].search([('order_id','=',commande.id)]) ###('display_type','=','')
                        pxtousok=0
                        for ligne in lignecommande:
                            if ligne.x_px_maj==False and not ligne.display_type:
                                pxtousok=pxtousok+1
                                if ligne.product_id==line.product_id and partner in line.product_id.seller_ids.mapped('name'):
                                    pourcentage=self.env['x_calculprix.detail'].search([('x_max','>=',price),('x_min','<=',price)]).x_marge
                                    ligne.update({'price_unit':price * (1 + (pourcentage/100)), 'x_px_maj':True})
                                    pxtousok=pxtousok-1
                                    # Mise à jour du prix de vente dans la fiche article
                                    # Mise à jour coût avec le dernier px d'achat /!\ attention ne met à jour que pour la société en cours pour le coût !!!!!!! ### MEP_07.1 
                                    self.env['product.template'].search([('id','=',line.product_id.product_tmpl_id.id)]).update({'list_price': price * (1 + (pourcentage/100)),'standard_price': price})

            #Changement du statut du devis client A envoyer
            if pxtousok==0:
                commande.write({'state': 'tosend'})
        # 3- Changement de statut de la commande en état Attente confirmation client            
            order.write({'state': 'wait'})
            
    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent', 'tosend']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step'\
                    or (order.company_id.po_double_validation == 'two_step'\
                        and order.amount_total < self.env.company.currency_id._convert(
                            order.company_id.po_double_validation_amount, order.currency_id, order.company_id, order.date_order or fields.Date.today()))\
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            # 1- Mise à jour de la liste de prix fournisseur
            if not order.origin:
                for line in self.order_line:
                # Do not add a contact as a supplier
                    partner = self.partner_id if not self.partner_id.parent_id else self.partner_id.parent_id
                    if line.product_id and partner in line.product_id.seller_ids.mapped('name'):              
                        # Convert the price in the right currency.
                        currency = partner.property_purchase_currency_id or self.env.company.currency_id
                        price = self.currency_id._convert(line.price_unit, currency, line.company_id, line.date_order or fields.Date.today(), round=False)
                        if line.product_id.product_tmpl_id.uom_po_id != line.product_uom:
                            default_uom = line.product_id.product_tmpl_id.uom_po_id
                            price = line.product_uom._compute_price(price, default_uom)
                        self.env['product.supplierinfo'].search([('name','=',partner.id),('product_tmpl_id','=',line.product_id.product_tmpl_id.id)]).update({'price': price})
                    # Mise à jour du prix de vente dans la fiche article
                    # + Mise à jour coût avec le dernier px d'achat /!\ attention ne met à jour que pour la société en cours pour le coût !!!!!!! ### MEP_07.1
                    pourcentage=self.env['x_calculprix.detail'].search([('x_max','>=',price),('x_min','<=',price)]).x_marge
                    self.env['product.template'].search([('id','=',line.product_id.product_tmpl_id.id)]).update({'list_price': price * (1 + (pourcentage/100)),'standard_price': price})
        return True
    
    
    def button_approve(self, force=False):
        self.write({'state': 'purchase', 'date_approve': fields.Datetime.now()})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        return {}

    def button_acompte(self):
        view_id = self.env.ref('account.view_account_payment_form').id

        ArticleCore = self.env['x_parametrage'].search([('x_code','=','ARTCORE')]).x_valeur

        CommandeCore = self.env['purchase.order.line'].search([('order_id','=',self.id), ('product_id','=',int(ArticleCore))])
        
        if CommandeCore:
            return {
                'name':'Acompte fournisseur',
                'view_type':'form',
                'view_mode':'tree',
                'views' : [(view_id,'form')],
                'res_model':'account.payment',
                'view_id':view_id,
                'type':'ir.actions.act_window',
                #'res_id':self.id,
                'target':'new',
                #'context':context,
                'context':{'default_payment_type':'outbound', 'default_partner_type':'supplier', 'default_partner_id':self.partner_id.id, 'default_communication':self.name
                           , 'default_x_acomptefrs':'t', 'default_x_acomptecore':'t'}
            }
        else:
            return {
                'name':'Acompte fournisseur',
                'view_type':'form',
                'view_mode':'tree',
                'views' : [(view_id,'form')],
                'res_model':'account.payment',
                'view_id':view_id,
                'type':'ir.actions.act_window',
                #'res_id':self.id,
                'target':'new',
                #'context':context,
                'context':{'default_payment_type':'outbound', 'default_partner_type':'supplier', 'default_partner_id':self.partner_id.id, 'default_communication':self.name
                           , 'default_x_acomptefrs':'t'}
            }

            
      

            
class XenonPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line' 
        
        #A voir si besoin
        #state = fields.Selection(related='order_id.state', store=True, readonly=False)
    #x_sale_line_id = Field.Integer()
                

                

                
 