from odoo import models, fields, api

class XenonCalculPrix(models.Model):
    _name='x_calculprix'
    _description="Calcul du prix de vente"
    
    x_libelle=fields.Char(string='Libelle', required=True)
    x_datedebut=fields.Date(string='Date de debut',required=True)
    x_datefin=fields.Date(string='Date de fin')
    x_detail_id=fields.One2many('x_calculprix.detail','x_liste_ids', string="detail")
    
    # MEP_09.1
    x_fournisseur=fields.Many2one('res.partner', string='Vendor', change_default=True, tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', x_company_id)]", help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    x_categ_id = fields.Many2one(
        'product.category',
        string='Catégorie d''article',
        change_default=True, group_expand='_read_group_categ_id',
        help="Select category for the current product")
    x_typeart = fields.Selection([
        ('consu', 'Consumable'),
        ('service', 'Service'),
        ('product', 'Product')], string='Type d''article',
        help='A storable product is a product for which you manage stock. The Inventory app has to be installed.\n'
             'A consumable product is a product for which stock is not managed.\n'
             'A service is a non-material product you provide.')
    x_company_id = fields.Many2one('res.company', 'Company', index=1)
    x_defaut = fields.Boolean(string="Marge par défaut", default=False, copy=False)
    
class XenonCalculPrixDetail(models.Model):
    _name='x_calculprix.detail'
    _description="Détail du calcul des prix de vente"
    
    x_liste_ids=fields.Many2one('x_calculprix',string="Liste", ondelete='cascade')
    x_min=fields.Float(string='Montant min', required=True)
    x_max=fields.Float(string='Montant max', required=True)
    x_marge=fields.Float(string='Pourcentage', required=True)
    
 
    
    
    