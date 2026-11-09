import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'darkwolf-backend'))
from app.db.mongodb import db
print('inventory_docs',db.leak_site_inventory.count_documents({}))
for field in ('status','availability'):
 print(field,list(db.leak_site_inventory.aggregate([{'$group':{'_id':'$'+field,'n':{'$sum':1}}},{'$sort':{'_id':1}}])))
print('captcha',list(db.leak_site_inventory.find({'captcha':True},{'_id':0,'group':1,'host':1,'status_reason':1})))
print('antibot',list(db.leak_site_inventory.find({'anti_bot':True},{'_id':0,'group':1,'host':1,'status_reason':1})))
print('observations_total',db.observations.count_documents({}))
print('sources_with_status',db.sources.count_documents({'status':{'$exists':True}}))
print('source_statuses',list(db.sources.aggregate([{'$match':{'status':{'$exists':True}}},{'$group':{'_id':'$status','n':{'$sum':1}}}])))
