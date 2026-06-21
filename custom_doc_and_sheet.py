import os
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/documents'
]

mcp = FastMCP("custom google workspace")

#Authentication
def get_google_services():
    """Authenticates and returns the Docs and Sheets services object."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json',SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json',scopes=SCOPES)
            # This will pop up a browser window on your machine
            creds = flow.run_local_server(port=0)

            with open('token.json', 'w') as token:
                token.write(creds.to_json())

    sheets_services=build('sheets','v4',credentials=creds)
    docs_services = build("docs",'v1',credentials=creds)

    return sheets_services, docs_services

sheets_services , docs_services = get_google_services()

# MCP Tools
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
    """Read the raw text from google docs"""
    try:
        #fetch the json tree
        doc = docs_services.documents().get(documentId = document_id).execute()

        #the content is a list of structural elements
        document_content = doc.get('body',{}).get('content',[])
        full_text = ""

        for d in document_content:
            if d.get('paragraph'):
                paragraph_element = d['paragraph'].get('elements',[])
                #iterate over the list
                for para_element in paragraph_element:
                    #check if element is textRun
                    if 'textRun' in para_element:
                        #extract the string content
                        content = para_element['textRun'].get('content','')
                        full_text+=content
        
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