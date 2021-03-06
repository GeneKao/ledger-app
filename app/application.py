#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" My bookkeeping app.

Example:
    To run this code using python3 on the console to
    start the flask server. and go to http://localhost:8000/

    python3 application.py
"""

from models import Base, User, Project, Ledger_Item

import random
import string
import httplib2
import json
import requests

from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   jsonify, url_for, flash, make_response)
from flask import session as login_session

from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

__author__ = "Gene Ting-Chun Kao"
__email__ = "kao.gene@gmail.com"

app = Flask(__name__)

APPLICATION_NAME = "My Bookkeeping App"
CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']

# Connect to Database and create database session
engine = create_engine('sqlite:///userAccountingLedger.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


@app.route('/gconnect', methods=['POST'])
def gconnect():
    """Google Oauth login."""
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1].decode('utf-8'))
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print("Token's client ID does not match app's.")
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: '
    output += '150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;">'
    flash("you are now logged in as %s" % login_session['username'])
    print("done!")
    return output


def createUser(login_session):
    """Create user.

    Args:
        login_session (obj): Login session.

    Returns:
        int: User ID.

    """
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    """Get user info from id.

    Args:
        user_id (int): User ID.

    Returns:
        obj: User object.

    """
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    """Get user ID from email.

    Args:
        email (str): User email.

    Returns:
        int: User ID.

    """
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except Exception:
        return None


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/logout')
def gdisconnect():
    """Google log out funciton."""
    access_token = login_session.get('access_token')
    if access_token is None:
        print('Access Token is None')
        response = make_response(json.dumps(
            'Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print('In gdisconnect access token is %s', access_token)
    print('User name is: ')
    print(login_session['username'])
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' \
          % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print('result is ')
    print(result)
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        # return response
        return redirect(url_for('showProjects'))
    else:
        response = make_response(json.dumps(
            'Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


def login_required(fn):
    @wraps(fn)
    def decorator(*args, **kwargs):
        if 'username' in login_session:
            return fn(*args, **kwargs)
        else:
            flash("You are not allowed to access there")
            return redirect(url_for('showLogin'))
    return decorator


@app.route('/login')
def showLogin():
    """Login page."""
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in range(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    # Render the login template
    return render_template('login.html', STATE=state)


# JSON APIs to view Project Information
@app.route('/project/<int:project_id>/ledger/JSON')
@login_required
def projectItemJSON(project_id):
    """Show a project in JSON format.

    Args:
        project_id (int): Project ID.

    Returns:
        str: A project in JSON.

    """
    items = session.query(Ledger_Item).filter_by(
        project_id=project_id).all()
    return jsonify(Ledgers=[i.serialize for i in items])


@app.route('/project/<int:project_id>/ledger/<int:ledger_id>/JSON')
@login_required
def ledgerItemJSON(project_id, ledger_id):
    """Show public ledger items in JSON format.

    Args:
        project_id (int): Project ID.
        ledger_id (int): Ledger ID.

    Returns:
        str: A Ledger in JSON.

    """
    item = session.query(Ledger_Item).filter_by(id=ledger_id).one()
    it = item.serialize

    if getUserInfo(item.user_id).id != login_session['user_id']:
        public_ledger = {'name': it['name'], 'description': it['description'],
                         'types': it['types'], 'id': it['id']}
        return jsonify(Ledger_Item=public_ledger)
    else:
        return jsonify(Ledger_Item=it)


@app.route('/project/JSON')
def projectJSON():
    """Show all projects in JSON format."""
    projects = session.query(Project).all()
    return jsonify(projects=[r.serialize for r in projects])


# Show all projects
@app.route('/')
@app.route('/project/')
def showProjects():
    """List all projects and render projects.html."""
    projects = session.query(Project).order_by(asc(Project.name))
    return render_template('projects.html', projects=projects)


# Create a new project
@app.route('/project/new/', methods=['GET', 'POST'])
@login_required
def newProject():
    """Create a new project.

    Returns:
        obj: If POST render project template, GET render newProject.html.

    """
    if request.method == 'POST':
        newProject = Project(
            name=request.form['name'], user_id=login_session['user_id'])
        session.add(newProject)
        flash('New Project %s Successfully Created' % newProject.name)
        session.commit()
        return redirect(url_for('showProjects'))
    else:
        return render_template('newProject.html')


# Edit a project
@app.route('/project/<int:project_id>/edit/', methods=['GET', 'POST'])
@login_required
def editProject(project_id):
    """Edit a project.

    Args:
        project_id (int): Project ID.

    Returns:
        obj: If GET render project template, POST render editProject.html.

    """
    editedProject = session.query(
        Project).filter_by(id=project_id).one()

    # only who edit this project can edit it.
    if getUserInfo(editedProject.user_id).id != login_session['user_id']:
        return json.dumps({'error': 'Only authorised user can edit this item'})

    if request.method == 'POST':
        if request.form['name']:
            editedProject.name = request.form['name']
            flash('Project Successfully Edited %s' % editedProject.name)
            return redirect(url_for('showProjects'))
    else:
        return render_template('editProject.html', project=editedProject)


# Delete a project
@app.route('/project/<int:project_id>/delete/', methods=['GET', 'POST'])
@login_required
def deleteProject(project_id):
    """Delete a project.

    Args:
        project_id (int): Project ID.

    Returns:
        obj: If POST render project template, GET render deleteProject.html.

    """
    projectToDelete = session.query(
        Project).filter_by(id=project_id).one()

    if getUserInfo(projectToDelete.user_id).id != login_session['user_id']:
        return json.dumps({'error':
                           'Only authorised user can delete this item'})

    if request.method == 'POST':
        session.delete(projectToDelete)
        flash('%s Successfully Deleted' % projectToDelete.name)
        session.commit()
        return redirect(url_for('showProjects', project_id=project_id))
    else:
        return render_template('deleteProject.html', project=projectToDelete)


# different ledger types, this is following N26 bank types.
ledger_types = ("ATM", "Bar_Restaurant", "Business expenses",
                "Cash", "Education", "Family_Friends", "Food_Groceries",
                "Healthcare_Drug_Stores", "Household_Utilities",
                "Income", "Insurance_Funances", "Leisure_Enterainment",
                "Media_Electronics", "Salary", "Saving_Investments",
                "Shopping", "Subsriptions_Donations",
                "Tax_Fines", "Transport_Car", "Travel_Holidays")


# Show a project ledger
@app.route('/project/<int:project_id>/')
@app.route('/project/<int:project_id>/ledger/')
@login_required
def showLedger(project_id):
    """Show a ledger.

    Args:
        project_id (int): Project ID.

    Returns:
        obj: If login ledger.html, else render publicledger.html.

    """
    project = session.query(Project).filter_by(id=project_id).one()
    creator = getUserInfo(project.user_id)
    items = session.query(Ledger_Item).filter_by(
        project_id=project_id).all()

    if 'username' not in login_session or \
            creator.id != login_session['user_id']:
        return render_template('publicledger.html',
                               items=items, project=project, creator=creator)
    else:
        return render_template('ledger.html',
                               items=items, project=project,
                               creator=creator, ledger_types=ledger_types)


# Create a new ledger item
@app.route('/project/<int:project_id>/ledger/new/', methods=['GET', 'POST'])
@login_required
def newLedgerItem(project_id):
    """Add a new ledger.

    Args:
        project_id (int): Project ID.

    Returns:
        obj: If POST render ledger template, GET render newLedgerItem.html.

    """
    project = session.query(Project).filter_by(id=project_id).one()

    if request.method == 'POST':
        newItem = Ledger_Item(name=request.form['name'],
                              description=request.form['description'],
                              types=request.form['types'],
                              cost=request.form['cost'],
                              date=request.form['date'],
                              project_id=project_id,
                              user_id=project.user_id)
        session.add(newItem)
        session.commit()
        flash('New Menu %s Item Successfully Created' % (newItem.name))
        return redirect(url_for('showLedger',
                                project_id=project_id))
    else:
        return render_template('newLedgerItem.html',
                               project_id=project_id,
                               ledger_types=ledger_types)


# Edit a ledger item
@app.route('/project/<int:project_id>/ledger/<int:ledger_id>/edit',
           methods=['GET', 'POST'])
@login_required
def editLedgerItem(project_id, ledger_id):
    """Edit a existing ledger.

    Args:
        project_id (int): Project ID.
        ledger_id (int): Ledger ID.

    Returns:
        obj: If POST render ledger template, GET render editLedgerItem.html.

    """
    editedItem = session.query(Ledger_Item).filter_by(id=ledger_id).one()
    project = session.query(Project).filter_by(id=project_id).one()

    if getUserInfo(editedItem.user_id).id != login_session['user_id']:
        return json.dumps({'error': 'Only authorised user can edit this item'})

    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['types']:
            editedItem.price = request.form['types']
        if request.form['cost']:
            editedItem.course = request.form['cost']
        if request.form['date']:
            editedItem.date = request.form['date']
        session.add(editedItem)
        session.commit()
        flash('Menu Item Successfully Edited')
        return redirect(url_for('showLedger', project_id=project_id))
    else:
        return render_template('editLedgerItem.html',
                               project_id=project_id, ledger_id=ledger_id,
                               item=editedItem, ledger_types=ledger_types)


# Delete a ledger item
@app.route('/project/<int:project_id>/ledger/<int:ledger_id>/delete',
           methods=['GET', 'POST'])
@login_required
def deleteLedgerItem(project_id, ledger_id):
    """Delete a ledger.

    Args:
        project_id (int): Project ID.
        ledger_id (int): Ledger ID.

    Returns:
        obj: If POST render ledger template, GET render deleteLedgerItem.html.

    """
    itemToDelete = session.query(Ledger_Item).filter_by(id=ledger_id).one()

    if getUserInfo(itemToDelete.user_id).id != login_session['user_id']:
        return json.dumps({'error':
                           'Only authorised user can delete this item'})

    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted')
        return redirect(url_for('showLedger', project_id=project_id))
    else:
        return render_template('deleteLedgerItem.html',
                               item=itemToDelete, project_id=project_id)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)
