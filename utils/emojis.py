"""Emoji used in embeds and buttons.

These can be emoji from ANY server. At startup utils/emoji_sync.py copies each one into the
bot's own application emoji (Developer Portal > Emojis) so it renders everywhere, even when the
bot is not in the emoji's server. To change one, paste the new `<:name:id>` (or `<a:name:id>`
for animated) here; plain unicode like "▶️" works too. The emoji must still exist on Discord.
"""

WARNING = "<a:Warning:1299512982006665216>"
TICK = "<:Ztick:1222750301233090600>"
ADD = "<:add_white:1205381455505661952>"
VOICE = "<:Voice:1279464563150032991>"
MUSIC = "<:gvMusic:1213831433219481722>"
LOADING = "<a:RedLoading:1246777916621197424>"
DENIED = "<:Denied:1294218790082711553>"

SPOTIFY = "<:olympus_spotify:1247724797983719464>"
JIOSAAVN = "<:jiosaavn:1306976886047375430>"
SOUNDCLOUD = "<:SoundCloud:1307002774738829413>"
YOUTUBE = "<:youtube:1204225318295052371>"

# Player control buttons
BTN_AUTOPLAY = "<:o_autoplay:1302170665670934549>"
BTN_PREVIOUS = "<:o_previous:1303944619800662137>"
BTN_PAUSE = "<:o_pause:1302172935951351821>"
BTN_RESUME = "<:o_resume:1302173145980997712>"
BTN_SKIP = "<:o_skip:1303944716605198336>"
BTN_LOOP = "<:o_loop:1302170497546715231>"
BTN_SHUFFLE = "<:o_shuffle:1302173399900229633>"
BTN_REWIND = "<:o_rewind:1302173207440261171>"
BTN_STOP = "<:o_pause:1303946981500125205>"
BTN_FORWARD = "<:o_forward:1302173256085671976>"
BTN_REPLAY = "<:o_replay:1302173332312952873>"
