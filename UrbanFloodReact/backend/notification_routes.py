from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
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

class SOSRequest(BaseModel):
    user_data: Dict[str, Any]
    evacuation_data: Dict[str, Any]
    location_data: Dict[str, Any]
    ai_report: Optional[str] = ""

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
    
    # Fallback to evacuated count if total is somehow missing from frontend
    if total_at_risk == 0 and evacuated_count > 0:
        total_at_risk = evacuated_count
        
    success_rate = (evacuated_count / total_at_risk * 100) if total_at_risk > 0 else 0.0
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    report_id = f"FERP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Format the AI Report as HTML if provided
    ai_report_html = ""
    if req.ai_report:
        formatted_text = req.ai_report
        # Basic markdown to HTML
        import re
        formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted_text)
        formatted_text = re.sub(r'_(.*?)_', r'<i>\1</i>', formatted_text)
        
        # Replace newlines with <br> for inline blocks where paragraphs don't break well
        blocks = formatted_text.split('\n\n')
        formatted_html = []
        for block in blocks:
            if block.strip():
                br_text = block.strip().replace('\n', '<br/>')
                formatted_html.append(f"<p style='margin: 8px 0; line-height: 1.5;'>{br_text}</p>")

        ai_report_html = f"""
        <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0d47a1;">
            <h3 style="color: #0d47a1; margin-top: 0;">🤖 Civic AI Expert Field Analysis</h3>
            {''.join(formatted_html)}
        </div>
        """

    subject = f"🚨 OFFICIAL FLOOD EVACUATION PLAN - {station_name} | Civic AI Report by {researcher_name}"
    
    map_html_section = f"<img src='data:image/png;base64,{map_image_base64}' style='max-width: 100%; height: auto; border: 2px solid #ddd; border-radius: 8px;' alt='Evacuation Route Map'/>" if map_image_base64 else "<p style='color: #666; font-style: italic;'>Map visualization not available</p>"

    email_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">🌊 OFFICIAL FLOOD EVACUATION PLAN</h1>
            <h2 style="margin: 10px 0 0 0; font-size: 18px; font-weight: normal;">Emergency Response Research Report - Civic AI Verified</h2>
        </div>
        
        <div style="padding: 30px; background: #f8f9fa; border-radius: 0 0 10px 10px;">
            <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                
                <h2 style="color: #1e3c72; border-bottom: 2px solid #1e3c72; padding-bottom: 10px;">📋 EXECUTIVE SUMMARY</h2>
                
                <div style="background: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; margin: 20px 0;">
                    <p><strong>Prepared by:</strong> {researcher_name} (Emergency Response Researcher)</p>
                    <p><strong>Research Validation:</strong> Civic AI Expert System</p>
                    <p><strong>Report Date:</strong> {timestamp}</p>
                    <p><strong>Location:</strong> {location_name}</p>
                    <p><strong>Station:</strong> {station_name}</p>
                </div>

                {ai_report_html}
                
                <h3 style="color: #d32f2f;">🎯 CRITICAL FINDINGS</h3>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Optimal Algorithm</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{algorithm}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Average Evacuation Time</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{evacuation_time:.1f} minutes</td>
                    </tr>
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Success Rate</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{success_rate:.1f}% ({evacuated_count}/{total_at_risk} people)</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; border: 1px solid #ddd; font-weight: bold;">Coordinates</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{lat:.6f}, {lon:.6f}</td>
                    </tr>
                </table>
                
                <h3 style="color: #d32f2f;">🗺️ EVACUATION ROUTE MAP</h3>
                <div style="text-align: center; margin: 20px 0;">
                    {map_html_section}
                </div>
                
                <h3 style="color: #d32f2f;">📊 RECOMMENDED ACTIONS</h3>
                <ol style="padding-left: 20px;">
                    <li><strong>Immediate Deployment:</strong> Implement the {algorithm} evacuation algorithm for optimal, AI-verified results.</li>
                    <li><strong>Resource Allocation:</strong> Position emergency vehicles along dynamically identified evacuation routes.</li>
                    <li><strong>Communication:</strong> Alert residents in the affected area using the provided exact coordinates.</li>
                    <li><strong>Monitoring:</strong> Establish checkpoints at safe centers to track evacuation progress in real-time.</li>
                    <li><strong>Coordination:</strong> Liaise with local emergency services under Civic AI tracking for seamless execution.</li>
                </ol>
                
                <div style="background: #d4edda; padding: 20px; border-left: 4px solid #28a745; margin: 25px 0;">
                    <h4 style="margin-top: 0; color: #155724;">📧 RESEARCHER CONTACT INFORMATION</h4>
                    <p style="margin: 5px 0;"><strong>Lead Researcher:</strong> {researcher_name}</p>
                    <p style="margin: 5px 0;"><strong>Email:</strong> {researcher_email}</p>
                    <p style="margin: 5px 0;"><strong>Institution:</strong> Emergency Response Research Division & Civic AI Desk</p>
                    <p style="margin: 5px 0;"><strong>Report ID:</strong> {report_id}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 2px solid #eee;">
                    <p style="font-size: 12px; color: #666; margin: 0;">
                        <strong>CONFIDENTIAL GOVERNMENT COMMUNICATION</strong><br>
                        This evacuation plan is generated using advanced AI algorithms by the Civic AI Expert and verified real-time flood simulation data.<br>
                        For immediate assistance or clarification, contact the research team or emergency services.
                    </p>
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
        formatted_text = req.ai_report
        import re
        formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted_text)
        formatted_text = re.sub(r'_(.*?)_', r'<i>\1</i>', formatted_text)
        formatted_lines = [f"<p style='margin: 5px 0;'>{line}</p>" for line in formatted_text.split("\n") if line.strip()]
        ai_report_html = f"""
        <div style="background-color: #f8d7da; color: #721c24; padding: 15px; margin-bottom: 20px; border-left: 4px solid #f5c6cb;">
            <h3 style="margin-top: 0;">📢 Civic AI Public Broadcast Message</h3>
            {''.join(formatted_lines)}
        </div>
        """

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

            <p><strong>🚨 IMMEDIATE EVACUATION ORDER FOR:</strong> {location_name}</p>
            <p><strong>🎯 Epicenter Coordinates:</strong> {lat:.6f}, {lon:.6f}</p>
            <p><strong>⏱️ Broadcast Timestamp:</strong> {timestamp}</p>
            
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
