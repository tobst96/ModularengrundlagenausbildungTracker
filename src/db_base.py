"""
Proxy for the modularized database layer. 
Imports everything from src.database and re-exports it to maintain backward compatibility.
"""
from .database import (
    get_connection, init_db, get_vehicles, create_incident_report, 
    get_active_incidents, create_active_incident, update_active_incident, close_incident
)
from .database import *
