{
    'name': 'Xenon Site Web',
    'version': '1.0',
	'author':"Laurent LOEZIC",
    'category': 'Site',
    'summary': 'Site web Xenon',
    'depends':['sale', 'sale_purchase', 'sale_stock', 'purchase', 'product', 'website', 'portal','web', 'theme_treehouse', 'theme_common'],
    'data': ['views/theme_xenon.xml', 'views/xenon_layout.xml'],
    'css' : ['static/src/css/theme_xenon.scss'],
	'demo':[],
    'installable': True,
}