import sys;sys.path.insert(0,"src")  
from sqlalchemy import create_engine, select  
from db.models import Account  
e=create_engine("postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/yelp_factory")  
with e.connect() as c:  
 rows=c.execute(select(Account)).scalars().all()  
 print("ORM select on RUNTIME yelp_factory ok, rows=",len(rows))  
