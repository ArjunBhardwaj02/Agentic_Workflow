import os
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
from datetime import datetime
import pytz
from email.message import EmailMessage

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets', #google sheet
    'https://www.googleapis.com/auth/documents',    #google docs
    'https://www.googleapis.com/auth/drive.readonly', #google drive -> read only
    'https://www.googleapis.com/auth/gmail.readonly',   #gmail read
    'https://www.googleapis.com/auth/gmail.compose', # gmail draft
    'https://www.googleapis.com/auth/calendar.events' #calendar
]

mcp = FastMCP("custom google workspace")

#Authentication
def get_google_services():
    """Authenticates and returns the Docs and Sheets services object."""

    access_token = os.environ.get("GOOGLE_ACCESS_TOKEN")
    
    if not access_token:
        raise ValueError("CRITICAL: No Google Access Token found. You must log in via the Streamlit sidebar.")
    creds = Credentials(token=access_token)
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json',SCOPES)
    
    # if not creds or not creds.valid:
    #     if creds and creds.expired and creds.refresh_token:
    #         creds.refresh(Request())
    #     else:
    #         flow = InstalledAppFlow.from_client_secrets_file('credentials.json',scopes=SCOPES)
    #         # This will pop up a browser window on your machine
    #         creds = flow.run_local_server(port=0)

    #         with open('token.json', 'w') as token:
    #             token.write(creds.to_json())

    sheets_services=build('sheets','v4',credentials=creds)
    docs_services = build("docs",'v1',credentials=creds)
    drive_services = build("drive",'v3',credentials=creds)
    gmail_services = build('gmail', 'v1', credentials=creds)
    calendar_services  = build('calendar', 'v3', credentials=creds)

    return sheets_services, docs_services,drive_services,gmail_services,calendar_services

sheets_services , docs_services, drive_services,gmail_services,calendar_services = get_google_services()

def extract_email_body(payload) -> str:
    """Recursively parses a Gmail API payload to extract plain text."""
    body = ""
    
    # Base case: if the current part contains data
    if 'data' in payload.get('body', {}):
        data = payload['body']['data']
        # Gmail uses urlsafe base64 encoding
        body += base64.urlsafe_b64decode(data).decode('utf-8')
        
    # Recursive case: if the email has multiple parts (text, html, attachments)
    if 'parts' in payload:
        for part in payload['parts']:
            # We only want to extract the plain text, ignore html and attachments for the LLM
            if part.get('mimeType') == 'text/plain':
                body += extract_email_body(part)
            elif 'parts' in part:
                # Dig deeper into nested parts
                body += extract_email_body(part)
                
    return body

# MCP Tools
#Get date-time
@mcp.tool()
async def get_current_time()->str:
    """Returns the exact current date and time in IST (Asia/Kolkata).
    Always use this tool first if you need to calculate 'today', 'tomorrow', or schedule events."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    return f"Current Date/Time (IST): {now.strftime('%Y-%m-%d %H:%M:%S')}\nISO 8601: {now.isoformat()}"


#Search the drive for the docs / sheet
@mcp.tool()
async def search_drive(file_name:str)->str:
    """
    Searches Google Drive for any file by its exact or partial name.
    Returns the File ID (Document ID or Spreadsheet ID) and its type.
    
    Args:
        file_name: The human-readable name of the file (e.g., 'Resume' or 'Budget').
    """
    try:
        #excluding the trash files
        query = f"name contains '{file_name}' and trashed=false"
        result = drive_services.files().list(
            q = query,
            pageSize = 5, #retrive only top 5
            fields = "files(id, name, mimeType)"    #mimeType for llm to differentiate b/w docs and sheet
        ).execute()

        items = result.get('files',[])
        if not items:
            return f'No Google Docs found matching the name "{file_name}"'
        
        #format the output
        output ="Found the following documents: \n"
        for item in items:
            if 'document' in item['mimeType']:
                file_type = "Google Docs"
            elif 'spreadsheet' in item['mimeType']:
                file_type = 'Google Sheet'
            else:
                file_type = "Other (PDF, Image,etc.)"
            output += f"Name: {item['name']} | ID: {item['id']} | Type: {file_type}\n"

        return output

    except Exception as e:
        return f"Error searching Google Drive: {str(e)}"


#Sheets MCP Server

@mcp.tool()
async def create_sheet(title:str)->str:
    """
    Creates a new, empty Google Sheet in the user's Drive.
    Returns the Spreadsheet ID, which is required to write data later.
    
    Args:
        title: The name of the new spreadsheet.
    """
    try:
        body = {
            'properties':{
                'title':title
            }
        }
        spreadsheet = sheets_services.spreadsheets().create(body=body).execute()

        #extract the ID
        sheet_id = spreadsheet.get('spreadsheetId')

        if not sheet_id:
            return "Error: Sheet created but failed to retrieve ID"
        
        return f"Success: Created sheet '{title}. IMPORTANT SPREADSHEET ID: {sheet_id}'"
    
    except Exception as e:
        return f"Error Creating Sheet: {str(e)}"

@mcp.tool()
async def read_sheet(spreadsheet_id:str, range_name:str) -> str:
    """
    Reads data from a specific Google Sheet.
    Example range_name: 'Sheet1!A1:E10'
    """
    try:
        sheet = sheets_services.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=spreadsheet_id,
            range = range_name
        ).execute()

        values = result.get('values',[])
        if not values:
            return "No Datat found in the specified range"
        
        formatted_data = '\n'.join([', '.join(map(str,row)) for row in values])
        return f'Sheet Data: \n{formatted_data}'
    
    except Exception as e:
        return f'Error reading sheet: {str(e)}'
    
@mcp.tool()
async def write_sheet(spreadsheet_id:str, range_name:str, row_values: list[str])->str:
    """
    Appends a single row of data to a Google Sheet.
    
    Args:
        spreadsheet_id: The ID of the Google Spreadsheet.
        range_name: The sheet name or range (e.g., 'Sheet1').
        row_values: A list of strings representing columns in order.
                    Example: ["Learn LangGraph", "Project Details", "", "Done"]
    """
    try:
        sheet=sheets_services.spreadsheets()

        # The LLM gives us a clean list like ['Learn LangGraph', 'Project Details']
        # We wrap it in an outer list to make it the 2D array Google expects.
        body = {
            'values': [row_values]
        }

        #Execute the API Call
        result = sheet.values().append(spreadsheetId = spreadsheet_id, range = range_name,valueInputOption ="USER_ENTERED",insertDataOption="INSERT_ROWS", body = body).execute()

        updated_cells = result.get('updatedCells',0)
        return f'Success: Updated {updated_cells} cells.'
    
    except Exception as e:
        return f'Error Writing to sheet: {str(e)}'

#Docs MCP servers

@mcp.tool()
async def read_docs(document_id:str)->str:
    """Read the raw text from google docs, including tables and complex layouts."""
    try:
        #fetch the json tree
        doc = docs_services.documents().get(documentId = document_id).execute()

        def extract_text(obj)->str:
            extracted = ""
            
            if isinstance(obj, dict):
                # In the Docs API, actual readable text is almost always stored under the key 'content'
                if 'content' in obj and isinstance(obj['content'], str):
                    extracted += obj['content']
                
                # Continue digging through all other nested dictionaries and lists
                for k, v in obj.items():
                    extracted += extract_text(v)
                    
            elif isinstance(obj, list):
                # If we hit a list of elements, dig into each one
                for item in obj:
                    extracted += extract_text(item)
            return extracted
        
        full_text = extract_text(doc.get('body', {}))
        
        if not full_text.strip():
            return "Document is empty or could not be parsed."
        return f"Document Content :\n{full_text}"
    
    except Exception as e:
        return f"Error reading document: {str(e)}"
    
@mcp.tool()
async def append_doc(document_id:str, text:str)->str:
    """
    Appends text to the very end of a Google Doc.
    
    Args:
        document_id: The ID from the Google Doc URL.
        text: The string of text to append.
    """

    try:
        #fetch the document

        #we are going to find the index of the 'last element - 1' to find the last index from where we have to append our text in the document

        doc = docs_services.documents().get(documentId  =document_id).execute()
        content = doc.get('body',{}).get('content',[])

        if not content:
            return "Error: Document structure not valid!"
        
        #Get the last element 's Index - 1
        lastelement = content[-1]
        end_index = lastelement.get('endIndex',1)-1

        #construct the highly nested batchUdpdate payload
        requests = [
            {
                "insertText":{
                    "location":{
                        "index":end_index
                    },
                    # inject a new line to append cleanly
                    'text': text + '\n'
                }
            }
        ]

        #execute the api call
        result = docs_services.documents().batchUpdate(
            documentId = document_id,
            body = {'requests':requests}
        ).execute()

        return f"Success: Appended text at index {end_index}"
    
    except Exception as e:
        return f"Error appending to document :{str(e)}"
    
@mcp.tool()
async def create_doc(title:str)->str:
    """
    Creates a new, empty Google Doc in the user's Drive.
    Returns the Document ID, which is required to append text later.
    
    Args:
        title: The name of the new document.
    """

    try:
        body={
            'title':title
        }
        #execute creating request
        doc = docs_services.documents().create(body=body).execute()

        #Extract new ID
        doc_id = doc.get('documentId')
        if not doc_id:
            return "Error: Document created but failed to retrieve ID"
        
        return f"Success: Created Document '{title}. IMPORTANT DOCUMENT ID: {doc_id}'"

    
    except Exception as e:
        return f'Error Creating the document : {str(e)}'
    
#for gmail
@mcp.tool()
async def create_email_draft(to_email:str,body_text:str,subject:str="")->str:
    """
    Creates an email draft in the user's Gmail account WITHOUT sending it.
    Always use this instead of send_email unless the user explicitly bypasses safety.
    """
    try:
        message = EmailMessage()
        message.set_content(body_text)
        message['To'] = to_email
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        #draft the mail
        draft_payload = {"message":{"raw":encoded_message}}
        draft = gmail_services.users().drafts().create(
            userId = "me",
            body = draft_payload
        ).execute()

        return f"Success: Draft safely created in your Gmail account. Draft ID: {draft['id']}"
    except Exception as e:
        return f"Error creating draft: {str(e)}"
    
@mcp.tool()
async def send_email(to_email:str,body_text:str , subject: str = "")->str:
    """Sends and email using the user 's Gmail account"""
    try:
        message = EmailMessage()
        message.set_content(body_text)
        message['To'] = to_email
        message['Subject'] = subject

        #encode message for google api
        encoded_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw" : encoded_msg}

        send_message = gmail_services.users().messages().send(
            userId = "me",
            body = create_message
        ).execute()
        return f"Success: Email sent to {to_email}. Message ID: {send_message['id']}"
    except Exception as e:
        return f"Error sending email: {str(e)}"

@mcp.tool()
async def search_email(query: str = "is:unread", max_results: int = 5)->str:
    """
    Searches the user's Gmail inbox. 
    Use standard Gmail search queries (e.g., 'from:john', 'subject:invoice', 'is:unread').
    Returns a summary of emails including their Message IDs.
    """
    try:
        results = gmail_services.users().messages().list(
            userId ='me',
            q = query,
            maxResults = max_results
        ).execute()
        messages = results.get('messages',[])
        if not messages:
            return f"No email found matching query: '{query}'"
        output = f"Found {len(messages)} emails:\n\n"

        for msg in messages:
            #fetch the metadata
            msg_data = gmail_services.users().messages().get(
                userId = 'me',
                id = msg['id'],
                format = 'metadata',
                metadataHeaders = ['Subject','From','Date']
            ).execute()

            headers = msg_data['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] =='Subject'), "No Subject")
            sender = next((h['value'] for h in headers if h['name'] == 'From'),'Unknown')
            output += f'- IDL {msg['id']}\n From: {sender}\n Subject: {subject}\n Snippet: {msg_data.get('snippet','')}\n\n'
        
        return output
    except Exception as e:
        return f"Error Searching Email: {str(e)}"
    
@mcp.tool()
async def read_email(message_id: str) -> str:
    """
    Reads the full, raw plain-text body of a specific email using its Message ID.
    """
    try:
        # We request the 'full' format to get the actual email body
        msg_data = gmail_services.users().messages().get(
            userId='me', id=message_id, format='full'
        ).execute()
        
        headers = msg_data['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
        
        body_text = extract_email_body(msg_data['payload'])
        
        if not body_text.strip():
            body_text = "[No plain text body found. Email might be pure HTML or images.]"
            
        return f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n\nBody:\n{body_text}"
        
    except Exception as e:
        return f"Error reading email: {str(e)}"
    
#Calendar
@mcp.tool()
async def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "") -> str:
    """
    Creates a new event in the user's primary Google Calendar.
    CRITICAL: start_time and end_time MUST be strictly in ISO 8601 format with the +05:30 timezone offset.
    Example: '2026-06-23T10:00:00+05:30'
    """
    try:
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Kolkata', 
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Kolkata',
            },
        }
        
        created_event = calendar_services.events().insert(
            calendarId='primary', 
            body=event
        ).execute()
        
        return f"Success: Event '{summary}' created. Link: {created_event.get('htmlLink')}"
    except Exception as e:
        return f"Error creating event: {str(e)}"

@mcp.tool()
async def get_todays_events() -> str:
    """
    Fetches the user's upcoming events from their Google Calendar.
    Returns the start time, end time, and summary of the next 10 events.
    """
    try:
        # Get current time in UTC (required by Google API)
        now = datetime.utcnow().isoformat() + 'Z'
        
        events_result = calendar_services.events().list(
            calendarId='primary', timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return 'No upcoming events found.'

        output = "Upcoming Events:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            output += f"- {start}: {event['summary']}\n"
            
        return output
    except Exception as e:
        return f"Error fetching calendar events: {str(e)}"