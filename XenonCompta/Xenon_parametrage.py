from odoo import models, fields, api

  
    
class Xenonparametrage(models.Model):
    _name='x_parametrage'
    _description="Paramétrage"
    
    x_code=fields.Char(string='code', required=True)
    x_libelle=fields.Char(string='libelle', required=True)
    x_valeur=fields.Char(string='valeur', required=True)
    x_commentaire=fields.Char(string='commentaire')
    x_company_id = fields.Many2one('res.company', 'Company', index=True, default=lambda self: self.env.company)
    #x_actif=fields.Boolean()
    
    
