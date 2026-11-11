import sys;sys.path.insert(0,"src")  
from sqlalchemy import create_engine, text  
ADMIN="postgresql+psycopg://postgres:8dr4ksIVtQpBnkwt9bARRvP5jeAaAthU@127.0.0.1:5433/postgres"  
c=create_engine(ADMIN).connect(); c.execution_options(isolation_level="AUTOCOMMIT")  
c.execute(text("DROP DATABASE IF EXISTS yf_qa_0013_scratch"))  
c.execute(text("CREATE DATABASE yf_qa_0013_scratch"))  
print("scratch created", flush=True)  
n=c.execute(text("select count(*) from yelp_factory_x")).scalar() if 0 else None  
print("prod account count:", c.execute(text("select 1")).scalar())  
