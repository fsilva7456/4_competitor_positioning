import os
import logging
from contextlib import asynccontextmanager
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
   # Startup
   logger.info("Starting up application...")
   logger.info("Checking environment variables...")
   if not all([os.getenv('OPENAI_API_KEY'), os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY')]):
       logger.error("Missing required environment variables!")
   else:
       logger.info("All required environment variables are set")
   yield
   # Shutdown
   logger.info("Shutting down application...")

# Initialize FastAPI with lifespan
app = FastAPI(lifespan=lifespan)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize Supabase client
supabase: Client = create_client(
   os.getenv('SUPABASE_URL'),
   os.getenv('SUPABASE_KEY')
)

class CompetitorResponse(BaseModel):
   id: int
   competitor_name: str
   competitor_positioning: Optional[str]

def get_market_positioning(competitor_name: str) -> str:
   """
   Use OpenAI to analyze the competitor's market positioning and target audience
   """
   logger.info(f"Analyzing market positioning for {competitor_name}")
   prompt = f"""Analyze {competitor_name}'s loyalty program market positioning and target audience.
   Consider:
   - Primary target demographic
   - Market positioning (premium, value, etc.)
   - Unique value proposition
   - How the loyalty program supports their market position
   
   Provide this as a single, well-formatted paragraph focusing on who they target and how they position themselves."""
   
   response = client.chat.completions.create(
       model="gpt-4",
       messages=[
           {"role": "system", "content": "You are a helpful assistant that analyzes market positioning and target audiences."},
           {"role": "user", "content": prompt}
       ]
   )
   
   return response.choices[0].message.content.strip()

def update_competitor_positioning(competitor_id: int, competitor_name: str) -> CompetitorResponse:
   """
   Update a competitor's row with their market positioning analysis
   """
   logger.info(f"Updating positioning analysis for competitor ID {competitor_id}: {competitor_name}")
   positioning = get_market_positioning(competitor_name)
   
   response = supabase.table('competitors').update({
       'competitor_positioning': positioning
   }).eq('id', competitor_id).execute()
   
   updated_competitor = response.data[0]
   logger.info(f"Successfully updated positioning analysis for {competitor_name}")
   
   return CompetitorResponse(**updated_competitor)

@app.get("/")
async def root():
   logger.info("Health check endpoint called")
   return {"status": "API is running"}

@app.post("/update-single/{competitor_id}")
async def update_single_competitor(competitor_id: int):
   """
   Update the market positioning analysis for a single competitor
   """
   try:
       logger.info(f"Received request to update competitor ID: {competitor_id}")
       
       # Get competitor details
       response = supabase.table('competitors').select('*').eq('id', competitor_id).execute()
       
       if not response.data:
           logger.error(f"No competitor found with ID {competitor_id}")
           raise HTTPException(status_code=404, detail="Competitor not found")
           
       competitor = response.data[0]
       updated_competitor = update_competitor_positioning(competitor_id, competitor['competitor_name'])
       
       return updated_competitor
       
   except Exception as e:
       logger.error(f"Error processing request: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-all")
async def update_all_competitors():
   """
   Update market positioning analysis for all competitors without analyses
   """
   try:
       logger.info("Starting batch update of all competitors")
       response = supabase.table('competitors').select('id, competitor_name').is_('competitor_positioning', 'null').execute()
       
       if not response.data:
           logger.info("No competitors found needing positioning analysis")
           return {"status": "No competitors found needing updates"}
       
       logger.info(f"Found {len(response.data)} competitors to process")
       updated_competitors = []
       
       for competitor in response.data:
           try:
               updated = update_competitor_positioning(competitor['id'], competitor['competitor_name'])
               updated_competitors.append(updated)
               logger.info(f"Successfully processed {competitor['competitor_name']}")
           except Exception as e:
               logger.error(f"Error processing {competitor['competitor_name']}: {str(e)}")
       
       return {
           "status": "success",
           "total_processed": len(updated_competitors),
           "updated_competitors": updated_competitors
       }
       
   except Exception as e:
       logger.error(f"Error in batch update: {str(e)}")
       raise HTTPException(status_code=500, detail=str(e))
