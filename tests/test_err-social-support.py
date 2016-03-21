import logging

from vcr import VCR

from errbot.backends.test import FullStackTest

config = {'TWITTER_CONSUMER_KEY': 'aaaaa',
          'TWITTER_CONSUMER_SECRET': 'bbbb',
          'TWITTER_OAUTH_TOKEN': 'ccccc',
          'TWITTER_OAUTH_SECRET': 'dddd',
          'TWITTER_SEARCH_QUERY': 'usopen',
          'ZENDESK_INSTANCE_URI': 'https://example.zendesk.com',
          'ZENDESK_USER': 'example@example.com',
          'ZENDESK_PASSWORD': 'derppassword'}

"""
config = {'TWITTER_CONSUMER_KEY': 'CX26EI7n7Ud7E0DruTuC2E4DT',
          'TWITTER_CONSUMER_SECRET':
          'brnx6QJjsMM89wFD9v1XmLNvUeqL4Iu6nCyANoZvGSYq6dGouy',
          'TWITTER_OAUTH_TOKEN':
          '10947242-mZRf6GQv0W30eOovmcuBHOAoc1KlDWUTWK5OBd88p',
          'TWITTER_OAUTH_SECRET': '1UDcbwGFDOuGXeK0fTqGxgYEMYqMFveg3EmqBohpwHOaL',
          'TWITTER_SEARCH_QUERY': 'usopen',
          'ZENDESK_INSTANCE_URI': 'https://example.zendesk.com',
          'ZENDESK_USER': 'example@example.com',
          'ZENDESK_PASSWORD': 'derppassword'}
"""

vcr = VCR(serializer='json',
          cassette_library_dir='tests/fixtures/cassettes',
          record_mode='once',
          filter_headers=['authorization'])


class TestSocialSupportWithoutConfiguration(FullStackTest):
    def setUp(self, extra_plugin_dir='.', logging_level=logging.INFO):
        super(TestSocialSupportWithoutConfiguration,
              self).setUp(extra_plugin_dir=extra_plugin_dir,
                          loglevel=logging_level)

    def test_no_configuration(self):
        plugin_list = self.bot.get_all_active_plugin_names()
        self.assertFalse("SocialSupport" in plugin_list)

    def test_wrong_configuration(self):
        self.bot.deactivate_plugin_by_name('SocialSupport')
        incomplete_configuration = {"TWITTER_CONSUMER_KEY": "xxxx"}
        self.bot.set_plugin_configuration('SocialSupport',
                                          incomplete_configuration)

        self.bot.activate_plugin('SocialSupport')

        plugin_list = self.bot.get_all_active_plugin_names()
        self.assertFalse("SocialSupport" in plugin_list)


class TestSocialSupport(FullStackTest):
    def setUp(self):
        super(TestSocialSupport, self).setUp(extra_plugin_dir='.',
                                             loglevel=logging.INFO)

        self.bot.set_plugin_configuration('SocialSupport', config)
        self.bot.activate_plugin('SocialSupport')

        self.plugin = self.bot.get_plugin_obj_by_name('SocialSupport')

    def assertCommand(self, command, response, **kwargs):
        self.bot.push_message(command)
        self.assertIn(response, self.bot.pop_message(**kwargs),
                      "Did not find expected response to command "
                      "{0}: {1}".format(command, response))


class TestSocialSupportUtilities(TestSocialSupport):
    @vcr.use_cassette('tweets.json', inject_cassette=True)
    def test_search_tweets(self, cassette):
        tweets = self.plugin.search_tweets(q=config['TWITTER_SEARCH_QUERY'])
        self.assertTrue(len(tweets) == 100)
        self.assertEquals(tweets[0].id, 640303466536148992)
        self.assertEquals(cassette.play_count, 7)

    @vcr.use_cassette('tweets.json', inject_cassette=True)
    def test_fetch_tweets(self, cassette):
        tweets = self.plugin.fetch_tweets()
        self.assertTrue(len(tweets) == 100)
        self.assertEquals(tweets[0].id, 640303466536148992)
        self.assertEquals(cassette.play_count, 7)

    @vcr.use_cassette('tweets.json')
    def test_load_tweets_into_queue_empty(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        self.assertEquals(len(self.plugin["SUPPORT_TRAINING_QUEUE"]), 100)

    @vcr.use_cassette('tweets.json')
    def test_load_tweets_into_queue_not_empty(self):
        self.plugin["SUPPORT_TRAINING_QUEUE"] = ["Item"]
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        self.assertEquals(len(self.plugin["SUPPORT_TRAINING_QUEUE"]), 101)

    @vcr.use_cassette('tweets.json')
    def test_pop_tweet_from_queue(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        tweet = self.plugin.pop_tweet_from_queue("SUPPORT_TRAINING_QUEUE")
        self.assertIn("Good luck to freshman Francesca Di Lorenzo", tweet)
        self.assertEquals(len(self.plugin["SUPPORT_TRAINING_QUEUE"]),
                          99)

    @vcr.use_cassette('tweets.json')
    def test_assign_tweet_to_trainer(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        tweet = self.plugin.pop_tweet_from_queue("SUPPORT_TRAINING_QUEUE")
        test = self.plugin.assign_tweet_to_trainer("Tester",
                                                   tweet)
        tweet_text = "RT @OhioState_WTEN: Good luck to freshman Francesca " \
                     "Di Lorenzo who opens play in @usopen juniors Sunday! " \
                     "http://t.co/b3a2m6S2BN #GoBucks ht…"
        self.assertEquals({"Tester": tweet_text}, test)

    def pop_tweet_for_trainer(self):
        self.plugin.assign_tweet_to_trainer("Tester", "I need help!")
        tweet = self.plugin.pop_tweet_for_trainer("Tester")

        self.assertEquals("I need help!", tweet)

    def test_update_corpus(self):
        self.plugin.update_corpus('SUPPORT_TRAINING_CORPUS',
                                  'I need help!',
                                  'pos')
        self.assertEquals([('I need help!', 'pos')],
                         self.plugin['SUPPORT_TRAINING_CORPUS'])

    def test_update_trainer_scoreboard_trainer_not_exist(self):
        self.plugin.update_trainer_scoreboard('Tester', 1)
        self.assertEquals({'Tester': 1},
                          self.plugin['TRAINER_SCOREBOARD'])

    def test_update_trainer_scoreboard_trainer_exist(self):
        self.plugin.update_trainer_scoreboard('Tester', 1)
        self.plugin.update_trainer_scoreboard('Tester', 2)
        self.assertEquals({'Tester': 3},
                          self.plugin['TRAINER_SCOREBOARD'])

    def test_retrieve_top_trainers(self):
        self.plugin.update_trainer_scoreboard('One', 1)
        self.plugin.update_trainer_scoreboard('Two', 2)
        self.plugin.update_trainer_scoreboard('Three', 3)
        self.plugin.update_trainer_scoreboard('Four', 4)
        self.plugin.update_trainer_scoreboard('Five', 5)
        self.plugin.update_trainer_scoreboard('Six', 6)

        test = self.plugin.retrieve_top_trainers()
        self.assertEquals(len(test), 5)
        self.assertEquals(('Six', 6), test[0])

    def test_retrieve_top_trainers_less_than_limit(self):
        self.plugin.update_trainer_scoreboard('One', 1)
        self.plugin.update_trainer_scoreboard('Two', 2)
        self.plugin.update_trainer_scoreboard('Three', 3)

        test = self.plugin.retrieve_top_trainers()
        self.assertEquals(len(test), 3)


class TestSocialSupportCommands(TestSocialSupport):
    @vcr.use_cassette('tweets.json')
    def test_train_status_uninitialized(self):
        self.bot.push_message("!train status")
        self.assertIn("No tweets found in training corpus",
                      self.bot.pop_message())
        self.assertIn("No tweets awaiting classification",
                      self.bot.pop_message())

    @vcr.use_cassette('tweets.json')
    def test_train_status_no_corpus(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        self.bot.push_message("!train status")
        self.assertIn("No tweets found in training corpus",
                      self.bot.pop_message())
        self.assertIn("Tweets awaiting classification: 100",
                      self.bot.pop_message())

    @vcr.use_cassette('tweets.json')
    def test_train_status(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        self.plugin.update_corpus('SUPPORT_TRAINING_CORPUS',
                                  'I need help!',
                                  'pos')

        self.plugin.update_trainer_scoreboard('One', 1)
        self.plugin.update_trainer_scoreboard('Two', 2)
        self.plugin.update_trainer_scoreboard('Three', 3)
        self.plugin.update_trainer_scoreboard('Four', 4)
        self.plugin.update_trainer_scoreboard('Five', 5)
        self.plugin.update_trainer_scoreboard('Six', 6)

        self.bot.push_message("!train status")
        self.assertIn("Training corpus size: 1",
                      self.bot.pop_message())
        self.assertIn("Tweets awaiting classification: 100",
                      self.bot.pop_message())
        self.assertEquals("Top 5 trainers:", self.bot.pop_message())
        self.assertEquals("1: Six - 6", self.bot.pop_message())
        self.assertEquals("2: Five - 5", self.bot.pop_message())
        self.assertEquals("3: Four - 4", self.bot.pop_message())
        self.assertEquals("4: Three - 3", self.bot.pop_message())
        self.assertEquals("5: Two - 2", self.bot.pop_message())

    @vcr.use_cassette('tweets.json')
    def test_train_gimme(self):
        self.plugin.load_tweets_into_queue("SUPPORT_TRAINING_QUEUE")
        self.bot.push_message("!train gimme")
        self.assertIn("Does the person submitting this tweet",
                      self.bot.pop_message())
        self.assertIn("Good luck to freshman Francesca Di Lorenzo",
                      self.bot.pop_message())
        tweet_text = "RT @OhioState_WTEN: Good luck to freshman Francesca " \
                     "Di Lorenzo who opens play in @usopen juniors Sunday! " \
                     "http://t.co/b3a2m6S2BN #GoBucks ht…"
        self.assertEquals({"gbin@localhost": tweet_text},
                          self.plugin['SUPPORT_TRAINER_QUEUE'])

    @vcr.use_cassette('tweets.json', inject_cassette=True)
    def test_train_gimme_empty_queue(self, cassette):
        self.assertCommand("!train gimme",
                           "No tweets awaiting classification")
