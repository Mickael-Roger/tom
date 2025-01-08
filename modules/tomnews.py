import requests
from datetime import datetime
import functools
from requests.auth import HTTPBasicAuth
import sqlite3
import threading
import time
from bs4 import BeautifulSoup


################################################################################################
#                                                                                              #
#                                          News                                                #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "news",
  "class_name": "TomNews",
  "description": "This module is used for for any question about the news."
}

class TomNews:

  def __init__(self, config, llm) -> None:

    self.url = config['url']
    self.username = config['user']
    self.password = config['password']

    self.db = config['cache_db']

    self.llm = llm

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        source TEXT,
        category TEXT,
        news_id INTEGER,
        author TEXT,
        read BOOLEAN DEFAULT 0,
        to_read BOOLEAN DEFAULT 0,
        title TEXT,
        summary TEXT,
        url TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "get_all_news",
          "description": "Retrieves a list of all unread news articles, organized by category. This function returns, the news_id, the news title, author and category.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "get_news_summary",
          "description": "Get the summary of a news article. This function must only be used when the user ask for a summary of a particular article.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "news_id": {
                "type": "string",
                "description": f"ID of the news you want to have a summary. The 'news_id' value, can be retreived from 'get_all_news' function.",
              },
            },
            "required": ["news_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "mark_news_as_read",
          "description": """Marks a specific news article as read.""",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "news_id": {
                "type": "string",
                "description": f"ID of the news you want to mark as read.",
              },
            },
            "required": ["news_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "mark_news_to_read",
          "description": "Mark a news to read it later.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "news_id": {
                "type": "string",
                "description": f"ID of the news you want to keep to read.",
              },
            },
            "required": ["news_id"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """
    Only if the user explicitly asks for a summary of an article, you should then use the 'get_news_summary' function otherwise, use the 'get_all_news' function.

    The function 'mark_news_as_read' is used in 3 scenarios:
       - When the user has already read the article and wants to remove it from the unread list.
       - When the user ask to mark as read an article
       - When the user is not interested in the article and does not plan to read it, but still wants to mark it as read to declutter the unread list.

    The function 'mark_news_to_read' is used in 2 scenarios:
       - When the user said he is interrested about an article
       - When the user ask to mark an article to be read later
    """
    self.complexity = 1
    self.functions = {
      "get_all_news": {
        "function": functools.partial(self.list_unread), 
        "responseContext": """Your response will be read aloud via text-to-speech, so it should be concise and free from any markdown formatting or URLs. It's important that you do not translate category names.
 
        When the question is about all categories, simply indicate the number of new news items in each category.
        
        If the user asks for more information about a specific category, only provide the titles and authors of the news in that category, without summarizing the articles.
        If there are more than two articles in a category, instead of providing a long list, give the title of one article and then offer the user the option to show the next one, and so on.

        It is important that you never use the function 'get_news_summary' unless the user explicitly ask for a summary of a particular article.        
        Your response must not include the URL of news articles; you should only provide the URL for a news article if the user explicitly requests it.
        If the user explicitly asks you to provide the link to the news, you must format it in HTML so that it is clickable and opens the link in a new window.
        If the user explicitly asks you to open or display the news, you must enclose the URL within the following tag: `Here is the news [open:PLACE URL HERE]`. This tag is interpreted by the frontend application, so, in this way, the news will be displayed automatically in a browser.
        """
      },
      "get_news_summary": {
        "function": functools.partial(self.get_news_summary), 
        "responseContext": "Your response will be read aloud via text-to-speech, so it should be concise and free from any markdown formatting or URLs." 
      },
      "mark_news_as_read": {
        "function": functools.partial(self.mark_as_read), 
        "responseContext": "" 
      },
      "mark_news_to_read": {
        "function": functools.partial(self.mark_as_read), 
        "responseContext": "" 
      },
    }


    self.thread = threading.Thread(target=self.thread_update)
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    

  def api_call(self, path, method, args=None):
    
    url = self.url + path

    if method == 'get':
      response = requests.get(url, auth=HTTPBasicAuth(self.username, self.password), params=args)
      if response.status_code == 200:
        return response.json()
      else:
        print(f"Error: {response.status_code}")
        return False

    elif method == 'post':
      response = requests.post(url, auth=HTTPBasicAuth(self.username, self.password), data=args)
      if response.status_code == 200:
        return response.json()
      else:
        print(f"Error: {response.status_code}")
        return False

    else:
      print(f"Method {method} unknown")
      return False


  def make_summary(self, news_id):

    llm_consign = []
    llm_consign.append({"role": "system", "content": "The user will submit a news article content. You must summarize it in a maximum of two lines."})

    # If it is a RSS feed and there is a content in the item
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT source, news_id, url FROM news WHERE id = ?", (news_id,))
    news = cursor.fetchone()
    dbconn.close()

    content = ""

    if news[0] == 'rss':
      id=int(news[1]) + 1
      val = self.api_call(path=f'/items', method='get', args={"batchSize": 1, "offset": id})
      if val != False:
        content = val['items'][0]['body']

    # Otherwise, try to get URL content
    if content == '':
      res = requests.get(news[2])

      if res.status_code == 200:
        content = res.text
      else:
        return False

    if content == '':
      return False


    soup = BeautifulSoup(content, 'html.parser')
    content_text = soup.get_text(separator=' ', strip=True)


    llm_consign.append({"role": "user", "content": content_text})

    response = self.llm.callLLM(llm_consign, llm='deepseek')

    print(response.choices[0].message.content)

    return response.choices[0].message.content





  def get_news_summary(self, news_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT title, summary, url FROM news WHERE id = ?", (news_id,))
    news = cursor.fetchone()
    dbconn.close()

    if news[1] == '' or news[1] is None:
      
      summary = self.make_summary(news_id=news_id)

      if summary == False:
        return {"status": "failure", "message": "Could not get a summary"}

      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("UPDATE news SET summary=? WHERE id = ?", (summary, news_id))
      dbconn.commit()
      dbconn.close()

    else:
      summary = news[1]

    return {"news_id": news_id, "title": news[0], "summary": summary, "url": news[2]}



  def mark_as_read(self, news_id):

    # Mark as read in the DB and delete its content.
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT news_id, source FROM news WHERE id = ?", (news_id,))
    news = cursor.fetchone()
    dbconn.close()

    # Mark it as read in the DB and delete content
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("UPDATE news SET read=1 WHERE id = ?", (news_id,))
    dbconn.commit()
    dbconn.close()

    res = True

    if news[1] == 'rss':
      # Mark it as read in the RSS app
      res = self.api_call(path=f"/items/{news[0]}/read", method='post')

    if res == False:
      return {"status": "failure", "message": "Could not mark news as read"}

    return {"status": "success", "message": "News marked as read"}




  def thread_update(self):
    self.news_update()
    while True:
      try:
        print("Update news ...")
        self.news_update()
      except:
        print("Fail to update RSS")

      time.sleep(300)


  def news_update(self):

    # List all RSS feed ID from current DB
    rss_ids = []
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT news_id FROM news WHERE source = 'rss'")
    ids = cursor.fetchall()
    dbconn.close()

    for id in ids:
      rss_ids.append(id[0])

    # Get all folders
    folders = {}
    res = self.api_call(path='/folders', method='get')
    if res:
      for folder in res['folders']:
        folder_id = folder['id']
        folders[folder_id] = folder['name']
    else:
      print("Could not list RSS folders")
      return False

    # Get all feeds
    feeds = {}
    res = self.api_call(path='/feeds', method='get')
    if res:
      for feed in res['feeds']:
        feed_id = feed['id']
        feed_name = feed['title']
        folder_id = feed['folderId']
        folder_name = folders[folder_id]
        feeds[feed_id] = {"source": feed_name, "category": folder_name}


    # Get all rss unread news
    val = self.api_call(path='/items', method='get', args={"getRead": "false", "type": 3, "id": 0})
    if val is not False:
      if val:
        for item in val['items']:
          if item['id'] not in rss_ids:
            # New news, insert into table
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("INSERT INTO news (source, category, news_id, author, title, url) VALUES ('rss', ?, ?, ?, ?, ?)", (feeds[item['feedId']]['category'], item['id'], feeds[item['feedId']]['source'], item['title'], item['url']))
            dbconn.commit()
            dbconn.close()

    else:
      print("Could not list RSS folders")
      return False



    







  def list_unread(self):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute("SELECT id, category, author, title, url  FROM news WHERE source = 'rss' AND read = 0")
    allnews = cursor.fetchall()
    dbconn.close()

    unread_news = {"category": {}}

    for news in allnews:
      id = news[0]
      category = news[1]
      author = news[2]
      title = news[3]
      url = news[4]
      if category not in unread_news['category'].keys():
        unread_news['category'][category] = []

      unread_news['category'][category].append({"news_id": id, "author": author, "title": title, "url": url})

    print("-------------------")
    print(unread_news)
    print("-------------------")
    
    if unread_news['category']:
      return unread_news
    else:
      return {"status": "success", "message": "No news"}

