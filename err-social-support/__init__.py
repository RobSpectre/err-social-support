import operator

from errbot import BotPlugin
from errbot import botcmd

from tweepy import OAuthHandler
from tweepy import API
from tweepy import Cursor

from zdesk import Zendesk


class SocialSupport(BotPlugin):
    """An err plugin for monitoring social channels by
       support organizations."""
    min_err_version = '3.0.0'

    def get_configuration_template(self):
        return {'TWITTER_CONSUMER_KEY': 'aaaaa',
                'TWITTER_CONSUMER_SECRET': 'bbbb',
                'TWITTER_OAUTH_TOKEN': 'ccccc',
                'TWITTER_OAUTH_SECRET': 'dddd',
                'TWITTER_SEARCH_QUERY': 'adcap',
                'ZENDESK_INSTANCE_URI': 'https://example.zendesk.com',
                'ZENDESK_USER': 'example@example.com',
                'ZENDESK_PASSWORD': 'derppassword'}

    def check_configuration(self, configuration):
        if configuration is not None:
            for key, value in self.get_configuration_template().items():
                if not configuration.get(key, None):
                    self.log.info("Configuration is missing required "
                                  "item: {0}".format(key))
                    return

            super(SocialSupport, self).check_configuration(configuration)

        return

    def activate(self):
        if self.config is None:
            self.log.info("SocialSupport is not configured - plugin not "
                          "activating.")
        else:
            # Configure clients
            auth = OAuthHandler(self.config['TWITTER_CONSUMER_KEY'],
                                self.config['TWITTER_CONSUMER_SECRET'])
            auth.set_access_token(self.config['TWITTER_OAUTH_TOKEN'],
                                  self.config['TWITTER_OAUTH_SECRET'])
            self.twitter_client = API(auth)
            self.since_id = None

            self.zendesk_client = Zendesk(self.config['ZENDESK_INSTANCE_URI'],
                                          self.config['ZENDESK_USER'],
                                          self.config['ZENDESK_PASSWORD'])

            self.log.info("Starting SocialSupport.")
            super(SocialSupport, self).activate()

            # Set up persistence.
            self.log.info("Setting up persistence.")
            self['SUPPORT_TRAINING_CORPUS'] = []
            self['SUPPORT_TRAINING_QUEUE'] = []
            self['SUPPORT_TRAINER_QUEUE'] = {}
            self['TRAINER_SCOREBOARD'] = {}

    def search_tweets(self, limit=100, **kwargs):
        tweets = []

        for tweet in Cursor(self.twitter_client.search, **kwargs).items(limit):
            self.since_id = tweet.id
            tweets.append(tweet)

        return tweets

    def fetch_tweets(self, limit=100, since_id=None, **kwargs):
        return self.search_tweets(q=self.config['TWITTER_SEARCH_QUERY'],
                                  limit=limit,
                                  since_id=since_id,
                                  **kwargs)

    def load_tweets_into_queue(self, queue):
        self.log.info("Loading tweets into {0}.".format(queue))
        if not self[queue]:
            self.log.info("No tweets found in {0}".format(queue))
            tweets = self.fetch_tweets()
            self[queue] = tweets
            self.log.info("Added {0} tweets to {1}".format(len(self[queue]),
                                                           queue))
        else:
            temp_queue = self[queue]
            self.log.info("{0} tweets found in {1}.".format(len(temp_queue),
                                                            queue))
            tweets = self.fetch_tweets()
            for tweet in tweets:
                self.log.debug("Adding tweet {0}.".format(tweet.id))
                temp_queue.append(tweet)
            self[queue] = temp_queue
            self.log.info("{0} tweets added to {1}.".format(len(tweets),
                                                            queue))

        return self[queue]

    def pop_tweet_from_queue(self, queue):
        temp_queue = self[queue]
        tweet = temp_queue.pop().text
        self[queue] = temp_queue

        return tweet

    def assign_tweet_to_trainer(self, trainer, tweet):
        temp_trainers = self['SUPPORT_TRAINER_QUEUE']
        temp_trainers[trainer] = tweet
        self['SUPPORT_TRAINER_QUEUE'] = temp_trainers
        return self['SUPPORT_TRAINER_QUEUE']

    def pop_tweet_for_trainer(self, trainer):
        temp_trainer = self['SUPPORT_TRAINER_QUEUE']

        if temp_trainer.get(trainer, None):
            tweet = temp_trainer[trainer]
            temp_trainer[trainer] = None

            self['SUPPORT_TRAINER_QUEUE'] = temp_trainer
            return tweet
        else:
            return None

    def update_corpus(self, corpus, tweet, classification):
        temp_corpus = self[corpus]
        temp_corpus.append((tweet, classification))
        self[corpus] = temp_corpus
        return self[corpus]

    def update_trainer_scoreboard(self, trainer, points=1):
        temp_scoreboard = self['TRAINER_SCOREBOARD']
        if temp_scoreboard.get(trainer, None):
            temp_scoreboard[trainer] += points
        else:
            temp_scoreboard[trainer] = points

        self['TRAINER_SCOREBOARD'] = temp_scoreboard
        return self['TRAINER_SCOREBOARD']

    def retrieve_top_trainers(self, limit=5):
        top_five = sorted(self['TRAINER_SCOREBOARD'].items(),
                          key=operator.itemgetter(1),
                          reverse=True)[:limit]
        return top_five

    def train_classifier_with_tweet(self, from_, tweet,
                                    classification):
        tweet = self.pop_tweet_for_trainer(from_)
        if tweet:
            scoreboard = self.update_trainer_scoreboard(from_)
            self.update_corpus("SUPPORT_TRAINING_CORPUS",
                               tweet,
                               classification)
            trainer_score = scoreboard[from_]
            return "Thank you for the training! Your score is now: " \
                   "{0}, {1}".format(str(trainer_score, from_))
        else:
            return "Have I given you a tweet to classify yet? Send !train " \
                   "gimme to receive one."

    @botcmd
    def train_status(self, message, args):
        if not self['SUPPORT_TRAINING_CORPUS']:
            yield "No tweets found in training corpus. Use !train to " \
                  "receive a tweet to classify."
        else:
            corpus_count = len(self['SUPPORT_TRAINING_CORPUS'])
            yield "Training corpus size: {0}".format(str(corpus_count))

        if not self['SUPPORT_TRAINING_QUEUE']:
            yield "No tweets awaiting classification - fetching more " \
                  "to classify."
            self.load_tweets_into_queue('SUPPORT_TRAINING_QUEUE')
        else:
            queue_count = len(self['SUPPORT_TRAINING_QUEUE'])
            yield "Tweets awaiting classification: {0}".format(str(queue_count))

        if self['TRAINER_SCOREBOARD']:
            yield "Top 5 trainers:"

            top_five = self.retrieve_top_trainers()

            counter = 1
            for trainer in top_five:
                yield "{0}: {1} - {2}".format(str(counter),
                                              trainer[0],
                                              str(trainer[1]))
                counter += 1

    @botcmd
    def train_gimme(self, message, args):
        if not self['SUPPORT_TRAINING_QUEUE']:
            yield "No tweets awaiting classification - fetching more " \
                  "to classify. Try !train gimme again to get a tweet to " \
                  "classify."
            self.load_tweets_into_queue('SUPPORT_TRAINING_QUEUE')
        else:
            tweet = self.pop_tweet_from_queue('SUPPORT_TRAINING_QUEUE')
            self.assign_tweet_to_trainer(message.frm.person, tweet)
            yield "Does the person submitting this tweet need technical " \
                  "support? Respond with !train yes or !train no."
            yield tweet
