from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key for sessions

# MongoDB Connection
client = MongoClient('mongodb://localhost:27017/')
db = client['twitter_clone']
users_collection = db['users']
tweets_collection = db['tweets']

# Helper functions
def get_user_by_username(username):
    return users_collection.find_one({'username': username})

def get_user_by_id(user_id):
    return users_collection.find_one({'_id': ObjectId(user_id)})

def get_tweets(limit=50):
    # Get tweets and sort by creation date (newest first)
    return tweets_collection.find().sort('created_at', -1).limit(limit)

def get_user_tweets(username, limit=50):
    # Get tweets from a specific user
    return tweets_collection.find({'username': username}).sort('created_at', -1).limit(limit)

def hash_password(password):
    # Simple password hashing
    return hashlib.sha256(password.encode()).hexdigest()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        # Get current user
        current_user = get_user_by_id(session['user_id'])
        # Get tweets from followed users and current user
        following = current_user.get('following', [])
        following.append(current_user['username'])  # Include user's own tweets
        
        tweets = list(tweets_collection.find({
            'username': {'$in': following}
        }).sort('created_at', -1).limit(50))
        
        # Get all users for the follow feature
        all_users = list(users_collection.find({}, {'username': 1, '_id': 0}))
        
        return render_template('index.html', tweets=tweets, 
                              current_user=current_user,
                              all_users=all_users)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Check if username already exists
        if get_user_by_username(username):
            flash('Username already exists')
            return redirect(url_for('register'))
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        # Create a new user
        new_user = {
            'username': username,
            'password': hash_password(password),
            'created_at': datetime.now(),
            'following': []  # List of usernames the user follows
        }
        
        users_collection.insert_one(new_user)
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = get_user_by_username(username)
        
        if user and user['password'] == hash_password(password):
            # Store user ID in session
            session['user_id'] = str(user['_id'])
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Clear session
    session.clear()
    return redirect(url_for('login'))

@app.route('/tweet', methods=['POST'])
def tweet():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    content = request.form['content']
    if not content or len(content) > 280:  # Twitter's character limit
        flash('Tweet must be between 1 and 280 characters')
        return redirect(url_for('index'))
    
    current_user = get_user_by_id(session['user_id'])
    
    # Create a new tweet
    new_tweet = {
        'username': current_user['username'],
        'user_id': session['user_id'],
        'content': content,
        'created_at': datetime.now(),
        'likes': []  # List of user IDs who liked this tweet
    }
    
    tweets_collection.insert_one(new_tweet)
    return redirect(url_for('index'))

@app.route('/delete_tweet/<tweet_id>')
def delete_tweet(tweet_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if the tweet belongs to the current user
    tweet = tweets_collection.find_one({'_id': ObjectId(tweet_id)})
    if tweet and tweet['user_id'] == session['user_id']:
        tweets_collection.delete_one({'_id': ObjectId(tweet_id)})
    
    return redirect(url_for('index'))

@app.route('/like_tweet/<tweet_id>')
def like_tweet(tweet_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    tweet = tweets_collection.find_one({'_id': ObjectId(tweet_id)})
    if tweet:
        # Check if user already liked this tweet
        if session['user_id'] in tweet.get('likes', []):
            # Unlike
            tweets_collection.update_one(
                {'_id': ObjectId(tweet_id)},
                {'$pull': {'likes': session['user_id']}}
            )
        else:
            # Like
            tweets_collection.update_one(
                {'_id': ObjectId(tweet_id)},
                {'$push': {'likes': session['user_id']}}
            )
    
    return redirect(url_for('index'))

@app.route('/follow/<username>')
def follow(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_user = get_user_by_id(session['user_id'])
    user_to_follow = get_user_by_username(username)
    
    if not user_to_follow or current_user['username'] == username:
        return redirect(url_for('index'))
    
    # Check if already following
    if username in current_user.get('following', []):
        # Unfollow
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$pull': {'following': username}}
        )
    else:
        # Follow
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$push': {'following': username}}
        )
    
    return redirect(url_for('index'))

@app.route('/profile/<username>')
def profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = get_user_by_username(username)
    if not user:
        return redirect(url_for('index'))
    
    current_user = get_user_by_id(session['user_id'])
    tweets = list(get_user_tweets(username))
    
    return render_template('profile.html', 
                          profile_user=user, 
                          tweets=tweets, 
                          current_user=current_user)

if __name__ == '__main__':
    app.run(debug=True)