import sys
import os
from bot.motor_reglas import analizar_filtracion_y_recomendar

leak_sbc = "[Leak] New POTM Mbappe SBC coming this friday. Requirements: 88 rated squad, 1 French player, 1 Ligue 1 player."
print(analizar_filtracion_y_recomendar(leak_sbc))
