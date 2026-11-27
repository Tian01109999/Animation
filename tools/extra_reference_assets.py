from import_reference_assets import character, plate, ANTS

plate('banh_bao_can_canh','Bánh bao · cận cảnh trao bằng tay',43.62,[580,270,1780,900],
 ['bánh bao','banh_bao','trao bánh','bun','steamed bun'],kind='inserts')
plate('hem_thanh_pho_dem','Hẻm thành phố ban đêm',19.48,[210,190,1620,930],
 ['hẻm','phố','đêm','alley','night','city'],tod='night')
plate('hanh_lang_cua_sat','Hành lang · cửa sắt',1271.54,[30,300,800,698],
 ['hành lang','cũ','cửa','corridor','wall'])
plate('duong_que_hoat_hinh','Đường quê · cây và bụi cỏ',36.29,[830,0,1920,650],
 ['đường quê','cỏ','cây','road','countryside'],source=ANTS,tod='day',style='stick')

# Replace the incomplete side-view man with the fully visible portrait.
character('nam_tre_ao_khoac','Nam trẻ · tóc ngắn · áo khoác tối',95.47,
 [(389,312),(392,252),(399,218),(407,207),(437,197),(443,186),(439,175),
  (429,159),(426,142),(431,119),(434,106),(447,98),(466,94),(483,98),
  (495,109),(503,130),(505,150),(501,164),(489,180),(488,195),(507,202),
  (522,203),(532,214),(535,246),(534,312)],200,'male','young',
 ['short black hair','dark jacket','tóc đen ngắn','áo khoác tối'])
character('nguoi_que_bac_si','Người que · nam trưởng thành · bác sĩ đeo kính',19.72,
 [(305,178),(294,168),(289,150),(294,130),(306,121),(326,120),(341,127),
  (347,141),(348,157),(342,170),(334,176),(335,188),(338,195),(356,184),
  (360,187),(338,203),(335,199),(337,246),(325,249),(332,302),(328,304),
  (320,261),(312,304),(307,303),(315,248),(302,248),(304,200),(300,203),
  (282,188),(284,184),(302,195),(306,188)],177,'male','adult',
 ['doctor','white coat','black hair','spiral glasses','arms raised','bác sĩ','áo choàng trắng','đeo kính','giơ tay'],
 source=ANTS,full_body=True,style='stick')
character('nguoi_que_tre_vuong_mien','Người que · bé trai · vương miện · đang cười',10.52,
 [(278,141),(275,115),(288,123),(297,112),(306,123),(321,119),(319,140),
  (328,152),(331,173),(321,188),(305,194),(304,201),(337,226),
  (313,251),(308,248),(330,226),(303,207),(302,260),(323,314),
  (318,316),(299,269),(282,316),(277,314),(296,259),(296,207),
  (269,228),(291,248),(287,252),(261,228),(296,200),(295,194),
  (280,188),(271,176),(271,156)],199,'male','child',
 ['child','crown','smiling','hands on hips','bé trai','vương miện','đang cười','tay chống hông'],
 source=ANTS,full_body=True,style='stick')
print('Portrait corrected; two existing stick figures extracted.')
