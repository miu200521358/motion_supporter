-------------------------------------------------
-------------------------------------------------

　「モーションサポーター　ローカル版」

　　β版用追加Readme

　　　　　　　　　　　　　　　　　miu200521358

-------------------------------------------------
-------------------------------------------------

----------------------------------------------------------------
■　配布元
----------------------------------------------------------------

　・ニコニコミュニティ「miuの実験室」
　　　https://com.nicovideo.jp/community/co5387214
　・ディスコード「MMDの集い　DISCORD支部」

　※基本的にβ版は上記二箇所でのみ配布しておりますので、上記以外で見かけたらお手数ですがご連絡下さい。

----------------------------------------------------------------
■　β版をご利用いただくにあたってのお願い
----------------------------------------------------------------

・この度はβ版テスターにご応募いただき、ありがとうございます
　β版をご利用いただくのにあたって、下記点をお願いいたします。

・不具合報告、改善要望、大歓迎です。
　要望についてはお応えできるかは分かりませんが…ｗ

　・不具合報告の場合、下記をご報告ください
　　・β版の番号（必須）
　　・メッセージ欄のコピペ、ログあり版でのログ、画面キャプチャのいずれか（必須）
　　・モーションとモデルのお迎えURL（分かれば、で構いません）
　　・ご報告は下記いずれかでお願いします。
　　　・コミュニティ　…　掲示板に投稿して下さい
　　　・ディスコード　…　ツール系雑談に投稿してください

・β版で作ったモーションの扱いは、リリース版と同様にお願いします。
　モーション・モデルの規約の範囲内であれば、
　どこに投稿していただいても、何に利用していただいても構いません。
　自作発言と再配布だけNG。年齢制限系は検索避けよろしくです。

・β版を使ってみて良かったら、ぜひ公開して、宣伝してくださいｗ
　励みになります！公開先はどこでもOKです。
　その際に、Twitterアカウント（@miu200521358）を添えていただけたら、喜んで拝見に伺います

----------------------------------------------------------------
■　rivision
----------------------------------------------------------------

MotionSupporter_1.06_β03 (2022/09/18)
新規追加
　・モーフ条件調整：　モーフを条件付きで比率補正します
　・捩りOFF：　捩りボーンの値を腕などに振り直します

MotionSupporter_1.03_β07 (2021/05/23)
・多段分割
　・値を残す（分割先が同じボーン）の場合に初期化しないよう処理追加

MotionSupporter_1.03_β06 (2021/05/22)
・多段分割
　・既に値が入っているボーンに対して回転成分を分割設定しようとした場合に、かけ算の順番が間違っていたので修正

MotionSupporter_1.03_β05 (2021/05/22)
・足FKtoIK
　・初期足首水平化チェック追加
　　・チェックを入れると、初期値（X=0, Y=0, Z=0）が設定されている足首ボーンの角度を地面と水平の角度に調整する
　・かかと・つま先Y=0チェック追加
　　・チェックを入れると、左右のかか・とつま先の4点のうちもっとも低いY値をY=0にセンターを調整する
　・接地固定指定追加
　　・指定すると、指定されたキーフレ範囲の軸足を、Y=0になるようセンターの高さを調節し、かつセンターXZを固定します。
　※いずれも未指定の場合は調整はせずにそのまま足FKをIKに変換する

MotionSupporter_1.03_β04 (2021/05/13)
・腕IKtoFK
　・腕IKで作成したキーをFKに置き換える機能
　・両用腕ＩＫ（ＦＫＩＫ）P.I.Pさん作　手首まで一通り対応




