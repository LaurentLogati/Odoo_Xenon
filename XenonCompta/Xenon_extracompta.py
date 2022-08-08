from odoo import models, fields, api

  
    
class Xenonextracompta(models.Model):
    _name='x_extracompta'
    _description="Données extracomptables"
    
    x_code=fields.Char(string='code', required=True)
    x_libelle=fields.Char(string='libelle', required=True)
    #x_valeur=fields.Char(string='valeur', required=True) #A supprimer
    x_balance=fields.Monetary(string='montant', default=0.0, currency_field='x_company_currency_id')
    x_commentaire=fields.Char(string='commentaire')
    x_company_id = fields.Many2one('res.company', 'Company', index=True, default=lambda self: self.env.company)
    x_date=fields.Date(string='Date',required=True)
    x_company_currency_id = fields.Many2one(related='x_company_id.currency_id', string='Company Currency',
        readonly=True, store=True,
        help='Utility field to express amount currency')
    #x_exercice=fields.Char(string='Exercice fiscal')
    #x_actif=fields.Boolean()
    
    
