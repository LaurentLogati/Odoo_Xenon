{
    'name': 'Xenon Ventes',
    'version': '1.0',
	'author':"Laurent LOEZIC",
    'category': 'Sales/Sales',
    'summary': 'Process de vente et achat Xenon',
	'depends':['sale', 'sale_purchase', 'sale_stock', 'purchase', 'product'],
    'data': ['xenon_sale_view.xml','xenon_purchase_view.xml', 'xenon_calcul_prix_view.xml','ir.model.access.csv','xenon_sale_report_templates.xml','xenon_sale_portal_templates.xml','xenon_report_invoice.xml', 'xenon_account_payment_view.xml', 'xenon_product_view.xml', 'xenon_stock_view.xml'],
	'demo':[],
    'installable': True,
}

