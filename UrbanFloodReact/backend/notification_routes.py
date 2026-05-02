from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from db import _get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

class EmergencyNotificationSystem:
    def __init__(self):
        self.alert_email = os.getenv("ALERT_EMAIL", "") # configure this
        self.alert_password = os.getenv("ALERT_PASSWORD", "")
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587

    def send_email_alert(self, recipient_email: str, subject: str, message: str, is_html: bool = False) -> bool:
        if not self.alert_email or not self.alert_password:
            logger.warning(f"Email credentials not configured. Mocking email to {recipient_email}")
            return True # Mock behaviour if credentials hold empty
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.alert_email
            msg['To'] = recipient_email
            msg['Subject'] = subject

            if is_html:
                msg.attach(MIMEText(message, 'html'))
            else:
                msg.attach(MIMEText(message, 'plain'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.alert_email, self.alert_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {recipient_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
            return False

# Pydantic models
class NotifyAuthoritiesRequest(BaseModel):
    researcher_data: Dict[str, Any]
    evacuation_data: Dict[str, Any]
    location_data: Dict[str, Any]
    ai_report: Optional[str] = ""
    map_image_base64: Optional[str] = None
    map_state: Optional[Dict[str, Any]] = None
    simulation_params: Optional[Dict[str, Any]] = None
    frontend_base_url: Optional[str] = "http://localhost:5173"

class SOSRequest(BaseModel):
    user_data: Dict[str, Any]
    evacuation_data: Dict[str, Any]
    location_data: Dict[str, Any]
    ai_report: Optional[str] = ""
    map_image_base64: Optional[str] = None
    map_state: Optional[Dict[str, Any]] = None
    simulation_params: Optional[Dict[str, Any]] = None
    frontend_base_url: Optional[str] = "http://localhost:5173"

def get_all_users_by_role(role: str):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    return list(db["users"].find({"role": role}, {"_id": 0, "password": 0}))

def get_all_users():
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    return list(db["users"].find({}, {"_id": 0, "password": 0}))

@router.post("/notify-authorities")
async def notify_authorities(req: NotifyAuthoritiesRequest):
    researcher_data = req.researcher_data
    evacuation_data = req.evacuation_data
    location_data = req.location_data
    map_image_base64 = req.map_image_base64
    
    authorities = get_all_users_by_role("authority")
    if not authorities:
        return {"total_sent": 0, "message": "No authorities found to notify"}

    researcher_name = researcher_data.get('name', 'Unknown Researcher')
    researcher_email = researcher_data.get('email', 'researcher@floodsystem.com')
    location_name = location_data.get('location_name', 'Unknown Location')
    station_name = location_data.get('station_name', location_name)
    lat = location_data.get('lat', 19.166624)
    lon = location_data.get('lon', 73.238906)
    
    algorithm = evacuation_data.get('algorithm', 'AI Computed')
    evacuation_time = float(evacuation_data.get('evacuation_time') or 0.0)
    evacuated_count = int(evacuation_data.get('evacuated_count') or 0)
    total_at_risk = int(evacuation_data.get('total_at_risk') or 0)
    base_url = req.frontend_base_url or "http://localhost:5173"
    
    # Fallback to evacuated count if total is somehow missing from frontend
    if total_at_risk == 0 and evacuated_count > 0:
        total_at_risk = evacuated_count
        
    success_rate = (evacuated_count / total_at_risk * 100) if total_at_risk > 0 else 0.0
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    report_id = f"FERP-{uuid.uuid4().hex[:8].upper()}"
    
    # Save report to MongoDB for interactive viewer
    db = _get_db()
    if db is not None:
        report_doc = {
            "report_id": report_id,
            "timestamp": timestamp,
            "researcher": researcher_name,
            "location": location_name,
            "evacuation_data": evacuation_data,
            "map_state": req.map_state,
            "simulation_params": req.simulation_params,
            "ai_report": req.ai_report
        }
        db["shared_reports"].insert_one(report_doc)

    # Format the AI Report as HTML if provided
    ai_report_html = ""
    if req.ai_report:
        import markdown
        html_content = markdown.markdown(req.ai_report)

        ai_report_html = f"""
        <div style="background: #fdfbf7; padding: 20px; border-radius: 8px; border-left: 4px solid #f39c12; margin-bottom: 25px;">
            <h3 style="margin-top: 0; color: #d35400; font-size: 16px; margin-bottom: 12px;">🤖 Civic AI Expert Field Analysis</h3>
            <div style="font-size: 14px; line-height: 1.6;">
                {html_content}
            </div>
        </div>
        """

    subject = f"🚨 OFFICIAL FLOOD EVACUATION PLAN - {station_name} | Civic AI Report by {researcher_name}"
    
    map_html_section = f"<img src='data:image/png;base64,{map_image_base64}' style='max-width: 100%; height: auto; border: 2px solid #ddd; border-radius: 8px;' alt='Evacuation Route Map'/>" if map_image_base64 else "<p style='color: #666; font-style: italic;'>Map visualization not available</p>"

    email_message = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #2c3e50; margin: 0; padding: 20px; background-color: #f4f7f6;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <div style="background: #2c3e50; color: white; padding: 30px 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 22px; letter-spacing: 1px;">🌊 OFFICIAL FLOOD EVACUATION PLAN</h1>
                <p style="margin: 8px 0 0 0; font-size: 14px; color: #bdc3c7;">Civic AI Verified Emergency Response</p>
            </div>
            
            <div style="padding: 30px;">
                <div style="margin-bottom: 25px;">
                    <p style="margin: 5px 0;"><strong>Report Date:</strong> {timestamp}</p>
                    <p style="margin: 5px 0;"><strong>Location:</strong> {location_name} ({station_name})</p>
                    <p style="margin: 5px 0;"><strong>Epicenter:</strong> {lat:.6f}, {lon:.6f}</p>
                </div>

                <div style="background: #eef2f5; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                    <h3 style="margin-top: 0; color: #2980b9; font-size: 16px; border-bottom: 2px solid #bdc3c7; padding-bottom: 8px;">Evacuation Metrics</h3>
                    <ul style="list-style: none; padding: 0; margin: 0;">
                        <li style="margin-bottom: 8px;"><strong>Algorithm:</strong> {algorithm}</li>
                        <li style="margin-bottom: 8px;"><strong>Avg. Time:</strong> {evacuation_time:.1f} mins</li>
                        <li><strong>Success Rate:</strong> {success_rate:.1f}% ({evacuated_count}/{total_at_risk} safely routed)</li>
                    </ul>
                </div>

                {ai_report_html}
                
                <h3 style="color: #2c3e50; font-size: 16px; margin-top: 30px; border-bottom: 2px solid #ecf0f1; padding-bottom: 8px;">Evacuation Route Map</h3>
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{base_url}/report/{report_id}" style="display: inline-block; padding: 12px 24px; background-color: #2980b9; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">🗺️ View Live Interactive Evacuation Map</a>
                    <p style="font-size: 11px; color: #7f8c8d; margin-top: 10px;">Click to view dynamic routes, flood layers, and transport logistics.</p>
                </div>
                
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #7f8c8d;">
                    <p style="margin: 0 0 5px 0;"><strong>Researcher:</strong> {researcher_name} ({researcher_email})</p>
                    <p style="margin: 0;"><strong>Report ID:</strong> {report_id}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


    notification_system = EmergencyNotificationSystem()
    results = {"authorities_notified": [], "failed": [], "total_sent": 0}

    for auth in authorities:
        email = auth.get('email')
        if email:
            success = notification_system.send_email_alert(email, subject, email_message, is_html=True)
            if success:
                results["authorities_notified"].append(email)
                results["total_sent"] += 1
            else:
                results["failed"].append(email)
    
    return results


@router.post("/sos")
async def mass_sos(req: SOSRequest):
    user_data = req.user_data
    evacuation_data = req.evacuation_data
    location_data = req.location_data
    
    # Needs to be sent to ALL users as it's a global SOS
    all_users = get_all_users()
    
    subject = "🚨 URGENT MASS SOS: AI-Calculated Evacuation Directive"
    
    authority_name = user_data.get('name', 'Central Authority')
    location_name = location_data.get('location_name', 'Affected Zones')
    algorithm = evacuation_data.get('algorithm', 'Safety Protocols')
    lat = location_data.get('lat', 19.166624)
    lon = location_data.get('lon', 73.238906)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")

    loc_lower = location_name.lower()
    local_instructions = "Stay calm. Do not panic. Move to higher ground or nearest safe center immediately."
    lang_header = "🚨 EMERGENCY FLOOD ALERT"
    
    if "maharashtra" in loc_lower or "mumbai" in loc_lower or "pune" in loc_lower:
        local_instructions += "<br/>शांत राहा. घाबरू नका. तत्काळ उंचीवर किंवा जवळच्या सुरक्षित केंद्रावर स्थलांतर करा."
        lang_header += "<br/>🚨 आणीबाणी पूर इशारा"
    elif "karnat" in loc_lower or "bangalore" in loc_lower or "bengaluru" in loc_lower:
        local_instructions += "<br/>शांतವಾಗಿರಿ. घाबरियागಬೇಡಿ. ತಕ್ಷಣ ಎತ್ತರದ ಪ್ರದೇಶ ಅಥವಾ ಹತ್ತಿರದ ಸುರಕ್ಷಿತ ಕೇಂದ್ರಕ್ಕೆ ತೆರಳಿ."
        lang_header += "<br/>🚨 ತುರ್ತು ಪ್ರವಾಹ ಎಚ್ಚರಿಕೆ"
    elif "delhi" in loc_lower or "hindi" in loc_lower:
        local_instructions += "<br/>शांत रहें। घबराएं नहीं। तुरंत ऊंचे स्थान या नजदीकी सुरक्षित केंद्र पर जाएं।"
        lang_header += "<br/>🚨 आपातकालीन बाढ़ चेतावनी"

    # Add AI generated report if present
    ai_report_html = ""
    if req.ai_report:
        import markdown
        html_content = markdown.markdown(req.ai_report)
        ai_report_html = f"""
        <div style="background-color: #f8d7da; color: #721c24; padding: 15px; margin-bottom: 20px; border-left: 4px solid #f5c6cb;">
            <h3 style="margin-top: 0;">📢 Civic AI Public Broadcast Message</h3>
            <div style="font-size: 14px; line-height: 1.6;">
                {html_content}
            </div>
        </div>
        """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    report_id = f"SOS-{uuid.uuid4().hex[:8].upper()}"

    # Save report to MongoDB for interactive viewer
    db = _get_db()
    if db is not None:
        report_doc = {
            "report_id": report_id,
            "timestamp": timestamp,
            "authority": authority_name,
            "location": location_name,
            "evacuation_data": evacuation_data,
            "map_state": req.map_state,
            "simulation_params": req.simulation_params,
            "ai_report": req.ai_report,
            "is_sos": True
        }
        db["shared_reports"].insert_one(report_doc)

    email_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="background-color: #dc3545; color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">{lang_header}</h1>
            <h2 style="margin: 10px 0 0 0; font-size: 18px; font-weight: normal;">Civic AI Directed Priority Evacuation</h2>
        </div>
        
        <div style="padding: 25px; border: 2px solid #dc3545; border-top: none; border-radius: 0 0 10px 10px;">
            <div style="background-color: #fff3cd; padding: 15px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                <strong>⚠️ MANDATORY CIVIC AI OVERRIDE:</strong> This is a global SOS broadcast initiated directly by {authority_name}. All personnel and citizens in the defined coordinates must evacuate.
            </div>

            {ai_report_html}

            <p style="margin-top: 15px;"><strong>🚨 IMMEDIATE EVACUATION ORDER FOR:</strong> {location_name}</p>
            <p><strong>🎯 Epicenter Coordinates:</strong> {lat:.6f}, {lon:.6f}</p>
            <p><strong>⏱️ Broadcast Timestamp:</strong> {timestamp}</p>
            
            <div style="text-align: center; margin: 25px 0;">
                <a href="{base_url}/report/{report_id}" style="display: inline-block; padding: 12px 24px; background-color: #dc3545; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">🗺️ View Live Interactive Evacuation Map</a>
            </div>
            
            <h3 style="color: #d32f2f; margin-top: 25px;">🚶‍♂️ EVACUATION PROTOCOLS:</h3>
            <ul>
                <li style="font-size: 16px; font-weight: bold; color: #d32f2f; margin-bottom: 10px;">{local_instructions}</li>
                <li>Proceed strictly via optimal routes provided in real-time by the <b>Civic AI {algorithm} System</b>.</li>
                <li>DO NOT deviate from AI-designated safe zones.</li>
                <li>Coordinate directly with on-ground <b>{authority_name}</b> teams.</li>
            </ul>
            
            <p style="margin-top: 25px;"><b>Please evacuate safely following prescribed routes. Do not panic. Our Digital Twin network is tracking the flood perimeter.</b></p>
        </div>
    </body>
    </html>
    """
    
    notification_system = EmergencyNotificationSystem()
    results = {"users_notified": [], "total_sent": 0}
    
    for u in all_users:
        if u.get('email'):
            success = notification_system.send_email_alert(u['email'], subject, email_message, is_html=True)
            if success:
                results["users_notified"].append(u['email'])
                results["total_sent"] += 1

    return results


@router.get("/shared-report/{report_id}")
async def get_shared_report(report_id: str):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    report = db["shared_reports"].find_one({"report_id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return report
