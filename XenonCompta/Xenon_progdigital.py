
import base64
import io

import logging
_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _
from odoo.exceptions import Warning
from odoo.tools import float_is_zero, pycompat

    
class Xenonprogdigital(models.Model):
    _name='x_progdigital'
    _description="Progdigital"
    
    x_nomclient=fields.Char(string='NomClient') #, required=True)
    x_immat=fields.Char(string='immat') #, required=True)
    x_maintenance=fields.Char(string='maintenance') #, required=True)
    x_lieu=fields.Char(string='lieu')
    x_hdevol=fields.Char(string='hDeVol') #, required=True)
    x_datecreation=fields.Date(string='dateCreation') #,required=True)
    #x_datecloture=fields.Date(string='dateCloture')
    x_datecloture=fields.Char(string='dateCloture') #Format texte à cause du "-" si pas clôturé
    x_entretien=fields.Char(string='entretien', required=True)
    x_typeentretien=fields.Char(string='typeEntretien', required=True)
    x_intervenant=fields.Char(string='intervenant', required=True)
    x_trigramme=fields.Char(string='trigramme', required=True)
    x_datesaisie=fields.Date(string='dateSaisie', required=True)
    x_hsaisie=fields.Char(string='hSaisie', required=True)
    
    x_encours_data = fields.Binary('Encours File', readonly=True, attachment=False)
    x_filename = fields.Char(string='Filename', size=256, readonly=True)
    
    
    
    def generate_export_encours(self):
        self.ensure_one()
        company = self.env.company
        
        header = [
            u'societe',     # 0
            u'anneemois',   # 1
            u'encours',     # 2
            u'textefin',    # 3
            ]
        
        
        rows_to_write = [header]
        
        sql_query = '''
        
        With base as (
            select T0.x_immat, T0.x_maintenance, T0.x_hdevol, T0.x_hsaisie, T2.name as societe, (cast(split_part(T0.x_hsaisie, ':', 2) as float)/60) as nbminute,
            cast(split_part(T0.x_hsaisie, ':', 1) as float) as nbheure,
            (cast(split_part(T0.x_hsaisie, ':', 1) as float) + (cast(split_part(T0.x_hsaisie, ':', 2) as float)/60)) as nbeheurenumeric,
            to_char(T0.x_datesaisie,'YYYY-MM') as AnneeMois
            from x_progdigital T0
            inner join account_analytic_account T1 on T1.name=T0.x_maintenance
            inner join res_company T2 on T2.id=T1.company_id
            where T0.x_datecloture='-' --and T0.x_immat='F-BNSQ'
            )

        Select societe, AnneeMois, sum(nbeheurenumeric) as Encours, '' as textefin
            from base
            group by societe, AnneeMois
            order by societe, AnneeMois
        '''
        
        #_logger.info('logLLO_sql_query' + str(sql_query))
        #self._cr.execute(
        #    sql_query, (self.x_date_from, self.x_date_to, company.id,self.x_date_from, self.x_date_to, company.id))
        self._cr.execute(sql_query)

        for row in self._cr.fetchall():
            rows_to_write.append(list(row))

        encoursvalue = self._csv_write_rows(rows_to_write)
        #end_date = fields.Date.to_string(self.x_date_to).replace('-', '')
        #start_date = fields.Date.to_string(self.x_date_from).replace('-', '')
        #suffix = ''
        #if self.x_export_type == "nonofficial":
        #    suffix = '-Brouillon compris'

        self.write({
            'x_encours_data': base64.encodestring(encoursvalue),
            # Filename = <siren>FECYYYYMMDD where YYYMMDD is the closing date
            'x_filename': 'EncoursProgdigital.txt',
            })

        action = {
            'name': 'ProgdigitalExportEncours',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=x_progdigital&id=" + str(self.id) + "&filename_field=x_filename&field=x_encours_data&download=true&x_filename=" + self.x_filename,
            'target': 'self',
            }
        return action
    
    
    def _csv_write_rows(self, rows, lineterminator=u'\r\n'):
        """
        Write FEC rows into a file
        It seems that Bercy's bureaucracy is not too happy about the
        empty new line at the End Of File.

        @param {list(list)} rows: the list of rows. Each row is a list of strings
        @param {unicode string} [optional] lineterminator: effective line terminator
            Has nothing to do with the csv writer parameter
            The last line written won't be terminated with it

        @return the value of the file
        """
        encoursfile = io.BytesIO()
        writer = pycompat.csv_writer(encoursfile, delimiter='|', lineterminator='')

        rows_length = len(rows)
        #_logger.info('logLLO_3' + str(rows))
        #_logger.info('logLLO_4' + str(rows_length))
        for i, row in enumerate(rows):
            #_logger.info('logLLO_2' + str(i) + str(row))
            if not i == rows_length - 1:
                row[-1] += lineterminator
            writer.writerow(row)

        encoursvalue = encoursfile.getvalue()
        encoursfile.close()
        return encoursvalue
    
    
    
    
    
