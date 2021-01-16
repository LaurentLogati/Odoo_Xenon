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
    


    def attente_client_confirm(self):
        for order in self:
            
        # 1- Mise à jour de la liste de prix fournisseur
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
                                self.env['product.template'].search([('id','=',line.product_id.product_tmpl_id.id)]).update({'list_price': price * (1 + (pourcentage/100))})
            
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
        return True
    
    
    def button_approve(self, force=False):
        self.write({'state': 'purchase', 'date_approve': fields.Datetime.now()})
        self.filtered(lambda p: p.company_id.po_lock == 'lock').write({'state': 'done'})
        return {}

            
      

            
class XenonPurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line' 
        
        #A voir si besoin
        #state = fields.Selection(related='order_id.state', store=True, readonly=False)
    #x_sale_line_id = Field.Integer()
                

                

                
 