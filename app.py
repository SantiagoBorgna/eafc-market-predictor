# print("Hola mundo")

import requests

#URL de un jugador de FutBin
url = "https://www.futbin.com/26/player/20801/lionel-messi"

#Realizamos la peticion
response = requests.get(url)

#Imprimimos el código de estado
print(f"Status Code: {response.status_code}")
print(response.text)

if response.status_code == 200:
    print("¡Conexión exitosa con FutBin!")
else:
    print(f"Algo pasó. Código: {response.status_code}")