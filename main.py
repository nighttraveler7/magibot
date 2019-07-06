from flask import Flask, request, abort

from linebot import (
	LineBotApi, WebhookHandler
)

from linebot.exceptions import (
	InvalidSignatureError
)

from linebot.models import (
	MessageEvent, TextMessage, TextSendMessage, FollowEvent
)

import os
import psycopg2
import nagisa

pp_list = ['は', 'って']
pronoun_list = [
	{'type': 'who', 'pronoun': 'だれ'},
	{'type': 'who', 'pronoun': '誰'},
	{'type': 'when', 'pronoun': 'いつ'},
	{'type': 'where', 'pronoun': 'どこ'},
	{'type': 'where', 'pronoun': '何処'},
	{'type': 'what', 'pronoun': 'なに'},
	{'type': 'what', 'pronoun': '何'},
	{'type': 'why', 'pronoun': 'なぜ'},
	{'type': 'why', 'pronoun': '何故'}
]

app = Flask(__name__)

DATABASE_URL = os.environ['DATABASE_URL']
YOUR_CHANNEL_ACCESS_TOKEN = os.environ['YOUR_CHANNEL_ACCESS_TOKEN']
YOUR_CHANNEL_SECRET = os.environ['YOUR_CHANNEL_SECRET']
DEBUG_MODE_PASSWORD = os.environ['DEBUG_MODE_PASSWORD']

line_bot_api = LineBotApi(YOUR_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(YOUR_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
	signature = request.headers['X-Line-Signature']
	body = request.get_data(as_text=True)
	app.logger.info("Request body: " + body)
	try:
		handler.handle(body, signature)
	except InvalidSignatureError:
		abort(400)

	return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
	reply_text = '友だち登録ありがとうございます！'
	line_bot_api.reply_message(
		event.reply_token,
		TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
	text = event.message.text
	user_id = event.source.user_id
	debug_mode_login = False
	verified = False

	reply_text = "ごめんなさい、その文章は理解できないの\n使い方を見るには'help'って送信してみて"

	conn = psycopg2.connect(DATABASE_URL, sslmode='require')
	conn.autocommit = True
	cur = conn.cursor()

	cur.execute("SELECT verified FROM admins WHERE user_id = %s", [user_id])
	result = cur.fetchone()

	if result is not None:
		(verified, ) = result
		if not verified:
			debug_mode_login = True

	if debug_mode_login:
		if text == DEBUG_MODE_PASSWORD:
			cur.execute("UPDATE admins SET verified = TRUE WHERE user_id = %s", [user_id])
			reply_text = "デバッグモードに入りました\n終了するには'exit'と打って送信してください"
		else:
			cur.execute("DELETE FROM admins WHERE user_id = %s", [user_id])
			reply_text = '合言葉が違います'
	else:
		if text == 'debug mode':
			if verified:
				reply_text = 'すでにデバッグモードですよ'
			else:
				cur.execute("INSERT INTO admins ( user_id ) values ( %s )", [user_id])
				reply_text = '合言葉を言ってね'
		elif text == 'help':
			f = open('help.txt', 'r')
			reply_text = f.read()
			f.close()
		elif (verified and text == 'exit'):
			cur.execute("DELETE FROM admins WHERE user_id = %s", [user_id])
			reply_text = 'デバッグモードを終了しました'
		else:
			cur.execute("SELECT question FROM questions")
			word_list = [i[0] for i in cur.fetchall()]

			tagger = nagisa.Tagger(single_word_list=word_list)
			words = tagger.tagging(text)

			if '助詞' in words.postags:
				pp_index = words.postags.index('助詞')
				pp = words.words[pp_index]

				if (pp in pp_list and '名詞' in words.postags[0:pp_index] and '代名詞' in words.postags[pp_index+1:len(words.postags)]):
					noun_index = words.postags.index('名詞', 0, pp_index)
					noun = words.words[noun_index]

					pronoun_index = words.postags.index('代名詞', pp_index+1, len(words.postags))
					pronoun = words.words[pronoun_index]

					for i in pronoun_list:
						if i['pronoun'] == pronoun:
							pronoun_type = i['type']

							cur.execute("SELECT answer_id FROM questions WHERE question = %s AND type = %s", [noun, pronoun_type])
							result = cur.fetchone()
							if result is not None:
								(answer_id, ) = result

								cur.execute("SELECT answer, sentence FROM answers WHERE id = %s", [answer_id])
								(answer, sentence) = cur.fetchone()

								if sentence is None:
									sentence = '{0[question]}は{0[answer]}よ'

								v = dict(question=noun, answer=answer)
								reply_text = sentence.format(v)

							break

	cur.close()
	conn.close()
	
	line_bot_api.reply_message(
		event.reply_token,
		TextSendMessage(text=reply_text))

if __name__ == "__main__":
	port = int(os.getenv("PORT", 5000))
	app.run(host="0.0.0.0", port=port)
