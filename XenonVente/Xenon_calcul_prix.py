from odoo import models, fields, api

class XenonCalculPrix(models.Model):
    _name='x_calculprix'
    _description="Calcul du prix de vente"
    
    x_libelle=fields.Char(string='Libelle', required=True)
    x_datedebut=fields.Date(string='Date de debut',required=True)
    x_datefin=fields.Date(string='Date de fin')
    x_detail_id=fields.One2many('x_calculprix.detail','x_liste_ids', string="detail")
    
class XenonCalculPrixDetail(models.Model):
    _name='x_calculprix.detail'
    _description="Détail du calcul des prix de vente"
    
    x_liste_ids=fields.Many2one('x_calculprix',string="Liste", ondelete='cascade')
    x_min=fields.Float(string='Montant min', required=True)
    x_max=fields.Float(string='Montant max', required=True)
    x_marge=fields.Float(string='Pourcentage', required=True)
    
 
    
    
    