import sys
from random import random
from operator import add
from datetime import datetime

from pyspark import SparkContext
from pyspark.mllib.classification import LogisticRegressionWithSGD
from pyspark.mllib.regression import LabeledPoint, LinearRegressionWithSGD
from numpy import array
import json

from vaderSentiment.vaderSentiment import sentiment as vaderSentiment

# Subtract 2 dates s2 - s1.  Dates are in string format.  Return difference
# in hours.
def subtract_dates(s2, s1):
    s_dates = [s2, s1]
    d_dates = []
    i = 0
    for s in s_dates:
        if '+' in s:
            head, sep, tail = s.partition('+')
            d_dates.append(datetime.strptime(head, "%Y-%m-%dT%H:%M:%S"))
        elif 'Z' in s:
            head, sep, tail = s.partition('Z')
            d_dates.append(datetime.strptime(head, "%Y-%m-%dT%H:%M:%S.%f"))
        else:
            d_dates.append(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f"))
        i += 1
    date_diff =abs(d_dates[0]-d_dates[1])
    hrs_diff = date_diff.days*24 + date_diff.seconds/3600.0 
    return hrs_diff
    
# Load the data from the json file into a dictionary
def load_data_from_file(sc, file_name):
    input = sc.textFile(file_name)
    data = input.map(lambda x: json.loads(x))
    print 'DATA COUNT: %d' % (data.count())
    #print data.first()
    return data

def get_sentiment(item, source):
    ''' Get the overall sentiment of the videos description '''
    
    if source == 'twitter':
        description = item['tweet']['orig_text']
    elif source == 'facebook':
        description = item['description']
    else:
        if dict['items'] != []:
            description = item['items'][0]['snippet']['description']
        else:
            description = ''
        
    description = description.encode('utf-8').strip()
    sent = vaderSentiment(description)
    
    item.setdefault("sentiment", sent['compound'])
    
    return item
    
# Load and parse the data into MLLib LabeledPoint data types
# Pull out the attributes that are required from the data source
def create_labeled_points_twitter(dict, reg_type):
    retweets = float(dict['tweet']['orig_retweet_count'])
    popularity = retweets
    if reg_type == 'logistic':    
        if popularity >= 158.0:
            popularity = 1.0
        else:
            popularity = 0.0
    video_length_sec = float(dict['tweet']['orig_video_length_ms'])/1000.0
    favorite_count = float(dict['tweet']['orig_favorite_count'])
    sentiment = dict['sentiment']
    last_index = len(dict['tweet']['rt_history']) - 1    
    time_hrs = subtract_dates(dict['tweet']['rt_history'][last_index]['rt_created_at'],
                              dict['tweet']['orig_created_at'])
    growth_rate = retweets / time_hrs
    features = [video_length_sec, favorite_count, growth_rate, sentiment]
    LP =  LabeledPoint(popularity, features)
    #print LP
    return LP

# Load and parse the data into MLLib LabeledPoint data types
# Pull out the attributes that are required from the data source
def create_labeled_points_facebook(dict, reg_type):
    total_likes = float(dict['total_likes'])
    popularity = total_likes
    if reg_type == 'logistic':    
        if popularity >= 496.0:
            popularity = 1.0
        else:
            popularity = 0.0
    video_length_sec = float(dict['length'])
    total_comments = float(dict['total_comments'])
    sentiment = dict['sentiment']
    last_index = len(dict['history']) - 1
    time_hrs = subtract_dates(dict['history'][last_index]['timestamp'],
                             dict['created_time'])
    growth_rate = total_likes / time_hrs
    features = [video_length_sec, total_comments, growth_rate, sentiment]
    LP =  LabeledPoint(popularity, features)
    #print LP
    return LP

# Filter out any YouTube data that does not contain the required fields
def filter_youtube_data(dict):
    if dict['items'] == []:
        return False
    elif 'contentDetails' not in dict['items'][0]:
        return False
    elif 'duration' not in dict['items'][0]['contentDetails']:
        return False
    return True

# Load and parse the data into MLLib LabeledPoint data types
# Pull out the attributes that are required from the data source
def create_labeled_points_youtube(dict, reg_type):
    view_count = float(dict['items'][0]['statistics']['viewCount'])
    popularity = view_count
    if reg_type == 'logistic':    
        if popularity >= 50790.0:
            popularity = 1.0
        else:
            popularity = 0.0
    video_length_sec = float(dict['items'][0]['contentDetails']['duration'])
    favorite_count = float(dict['items'][0]['statistics']['favoriteCount'])
    sentiment = dict['sentiment']
    last_index = len(dict['items'][0]['stats_history']) - 1
    time_hrs = subtract_dates(dict['items'][0]['stats_history'][last_index]['timestamp'],
                             dict['items'][0]['snippet']['publishedAt'])
    growth_rate = view_count / time_hrs
    features = [video_length_sec, favorite_count, growth_rate, sentiment]
    LP =  LabeledPoint(popularity, features)
    #print LP
    return LP

# Perform Spark prediction
def spark_prediction():
    """
        Spark Prediction
    """
    # Set this variable to distinguish between logistic and linear regression
    REGRESSION_TYPE = 'logistic'
    
    sc = SparkContext(appName="SparkPrediction")

    # load Twitter data
    twitter_data = load_data_from_file(sc, "file:///root/mongoData/small_twitter.json")
    #twitter_data = load_data_from_file(sc, "file:///root/mongoData/twitter.json")

    # load YouTube data
    youtube_data = load_data_from_file(sc, "file:///root/mongoData/small_youtube.json")
    #youtube_data = load_data_from_file(sc, "file:///root/mongoData/youtube.json")
    youtube_data = youtube_data.filter(filter_youtube_data)

    # load Facebook data
    facebook_data = load_data_from_file(sc, "file:///root/mongoData/small_facebook.json")
    #facebook_data = load_data_from_file(sc, "file:///root/mongoData/facebook.json")

    sent_twitter_data = twitter_data.map( lambda x: get_sentiment(x, 'twitter'))
    sent_youtube_data = youtube_data.map( lambda x: get_sentiment(x, 'youtube'))
    sent_facebook_data = facebook_data.map( lambda x: get_sentiment(x, 'facebook'))
    
    #create MLLib LabeledPoints
    twitter_LP = sent_twitter_data.map(lambda x: create_labeled_points_twitter(x, REGRESSION_TYPE))
    youtube_LP = sent_youtube_data.map(lambda x: create_labeled_points_youtube(x, REGRESSION_TYPE))
    facebook_LP = sent_facebook_data.map(lambda x: create_labeled_points_facebook(x, REGRESSION_TYPE))

    #combine all 3 datasets with the RDD.union command
    #all_LP = twitter_LP
    #all_LP = twitter_LP.union(facebook_LP)
    all_LP = twitter_LP.union(facebook_LP).union(youtube_LP)

    #NEED TO SHUFFLE THE DATA BEFORE SPLITTING

    # split data in to training (80%) and test(20%) sets
    train_LP, test_LP = all_LP.randomSplit([0.8, 0.2], seed=0)

    # Build logistic regression model
    model_log = LogisticRegressionWithSGD.train(train_LP)

    # Evaluate the model on training data
    preds_train_log = train_LP.map(lambda p: (p.label, model_log.predict(p.features)))
    total_train = float(train_LP.count())
    trainErr_log = preds_train_log.filter(lambda (v, p): v != p).count() / total_train
    
    # Evaluate the model on test data
    preds_test_log = test_LP.map(lambda p: (p.label, model_log.predict(p.features)))
    total_test = float(test_LP.count())
    testErr_log = preds_test_log.filter(lambda (v, p): v != p).count() / total_test

    print('ALL LP COUNT %d' % (all_LP.count()))
    print("Train Error = " + str(trainErr_log))
    print("Test Error = " + str(testErr_log))

    # Build linear regression model
    #model_lin = LinearRegressionWithSGD.train(all_LP)

    # Evaluate the model on training data
    #labels_and_preds_lin = all_LP.map(lambda p: (p.label, model_lin.predict(p.features)))
    #print labels_and_preds_lin
    #print labels_and_preds_lin.count()
    #total = labels_and_preds_lin.count()
    #MSE = labels_and_preds_lin.map(lambda (v, p): (v - p)**2).reduce(lambda x, y: x + y) / total
    #print("Mean Squared Error = " + str(MSE))

    sc.stop()

if __name__ == "__main__":

    spark_prediction()

