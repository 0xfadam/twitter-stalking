import re, os, time, sys, json
import argparse, requests
import sqlite3
import subprocess
from datetime import date,timedelta
from variables import *
from subprocess import DEVNULL, STDOUT, check_call
headers={'content-type': 'application/json'}

def difference (list1, list2):
   list_dif = [i for i in list1 + list2 if i not in list1 or i not in list2]
   return list_dif

def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)
    return conn

def create_db(conn):
    createContentTable="""CREATE TABLE IF NOT EXISTS results (
            id integer PRIMARY KEY,
            influencer text NOT NULL,
            id_str text NOT NULL,
            screen_name text NOT NULL,
            follow_date text,
            unfollow_date text,
            toIgnore INTEGER NOT NULL);"""
    try:
        c = conn.cursor()
        c.execute(createContentTable)
    except Error as e:
        print(e)


# content is a Tuple depending on query value
def insert_content(conn, query, content):
    time.sleep(1)
    if query is "import_friend":
        sql = ''' INSERT INTO results(influencer,id_str,screen_name,follow_date,toIgnore) VALUES(?,?,?,?,0) '''
    cur = conn.cursor()
    cur.execute(sql, content)
    return cur.lastrowid

def newInfluencer(conn, influencer):
    friendsList=getFriendsIDs(influencer)
    today = date.today()
    dateUpdate=str(today.year) + "-" + str(today.month) + "-" + str(today.day)
    for friend in friendsList:
        screen_name=convertIDtoScreenName(conn,friend)
        content=(influencer,friend,screen_name,dateUpdate)
        insert_content(conn,"import_friend",content)
        conn.commit()

def getFriendsFromDB(conn,influencer):
    cur = conn.cursor()
    friendsList_DB = []
    cur.execute("SELECT id_str FROM results WHERE influencer = \"%s\"" % influencer)
    sql_DB = cur.fetchall()
    for friends in sql_DB:
        friendsList_DB.append(friends[0])
    return friendsList_DB

def getFriendsIDs(influencer):
    IDS_list=[]
    #Regex to capture the friends IDs without all the surrounding bullshit
    regex_ids_lookup = r"\[.*\]"
    lookup="/1.1/friends/ids.json?screen_name=%s" % influencer
    proc=subprocess.Popen(('/usr/local/bin/twurl',lookup), stdout=subprocess.PIPE)
    #Raw results
    data = str(proc.stdout.read())
    if "Rate limit exceeded" in data:
        print("[-] Rate limit error, please try again")
        sys.exit(-1)
    #Regex to filter data
    ids_matches = re.finditer(regex_ids_lookup, data, re.MULTILINE | re.DOTALL)
    for ids_matchNum, ids_match in enumerate(ids_matches, start=1):
        for element in ids_match.group().split (","):
                #For First ans last element, "[" and "]" to eliminate
                if "[" in element:
                        element=element.replace('[', '')
                if "]" in element:
                        element=element.replace(']', '')
                IDS_list.append(element)

    return IDS_list

def isIDexisting(conn,id_str):
    cur = conn.cursor()
    cur.execute("SELECT screen_name FROM results WHERE id_str = %s" % id_str)
    rows = cur.fetchall()
    return rows

def convertIDtoScreenName(conn,element):
    #We may know the friend from other influencers. We check in DB before consuming API
    isFriendKnown=isIDexisting(conn,element)
    if len(isFriendKnown) != 0:
        print("This ID is known and corresponds to : %s" % isFriendKnown[0][0])
        return str(isFriendKnown[0][0])
    # If unknown, we query API
    #Retrieve ID of the persona
    lookup="/1.1/users/lookup.json?user_id=%d" % int(element)
    # Getting all info about the persona
    proc=subprocess.Popen(('/usr/local/bin/twurl',lookup), stdout=subprocess.PIPE)
    output = proc.stdout.read()
    if "Rate limit exceeded" in str(output):
        print("[-] Rate limit error, please try again")
        sys.exit(-1)
    #Regex to capture the screen name only (is put in group 1
    regex_screen_name = r"\"screen_name\":(?:\")(.*?)(?:\",\"location\")"
    screen_name_matches = re.finditer(regex_screen_name, str(output), re.MULTILINE | re.DOTALL)
    for screen_name_matchNum, screen_name_match in enumerate(screen_name_matches, start=1):
        # Personal Screen name found!
        return str(screen_name_match.group(1))

#Synchronization of everyone
def global_synchronize(conn):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT influencer from results;")
    rows = cur.fetchall()
    for influencer in rows:
        print(influencer[0])
        synchronize(conn, influencer[0])

def send_notif(friend):
  params_raw = {"text": friend }
  params = json.dumps(params_raw)
  r = requests.post(SLACK_URI, data=params, headers=headers, verify=False)
  
#Synchronization of one influencer
def synchronize(conn, influencer):
    today = date.today()
    dateUpdate=str(today.year) + "-" + str(today.month) + "-" + str(today.day)
    friendsList_API=getFriendsIDs(influencer)
    friendsList_DB=getFriendsFromDB(conn,influencer)
    #print(friendsList_API)
    #print(friendsList_DB)
    new_friends = [v for v in friendsList_API if v not in friendsList_DB]
    removed_friends = [v for v in friendsList_DB if v not in friendsList_API]
    for friend in new_friends:
        #print(friend)
        screen_name=convertIDtoScreenName(conn,friend)
        if screen_name:
            #print(screen_name)
            content=(influencer,friend,screen_name,dateUpdate)
            insert_content(conn, "import_friend", content)
            conn.commit()
            send_notif("@" + str(influencer) + ": "  + "https://twitter.com/" + str(screen_name))
            
def main():
    database = r"/opt/stalking/sqlite.db"
    conn = create_connection(database)

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--create','-c', help='Create Database', action='store_true')
    group.add_argument('--insert','-i', help='Insert Influencer', action='store_true')
    group.add_argument('--synchronize','-s', help='Synchronization of one influencer', action='store_true')
    group.add_argument('--global_synchronize','-gs', help='Synchronization of ALL influencers', action='store_true')
    
    parser.add_argument('--influencer', '-I')
    args = parser.parse_args()
    if (args.create):
        print("[+] Creating Database")
        create_db(conn)
    elif (args.insert):
        if(args.influencer is None ):
            parser.error("--influencer requires influencer")
        else:
            newInfluencer(conn, args.influencer)
    elif (args.synchronize):
        if(args.influencer is None ):
            parser.error("--influencer requires influencer")
        else:
            synchronize(conn, args.influencer)
    elif (args.global_synchronize):
            global_synchronize(conn)
            
if __name__ == "__main__":
        main()

