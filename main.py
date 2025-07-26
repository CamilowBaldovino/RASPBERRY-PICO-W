import network
import gc
import usocket as socket
import urequests as requests
import ujson
import json  # Usar json en lugar de ujson
import time
import machine  # Importa el módulo machine para reiniciar el sistema
import uos  # Usar 'uos' en lugar de 'os' en MicroPython
import struct
from machine import Pin, UART, Timer
from micropyGPS import MicropyGPS

# Archivos de almacenamiento
archivo_csv = "/datos_gps_sensor.csv"
archivo_wifi = "/credenciales_wifi.txt"
archivo_indice = "/ultimo_indice.txt"  # Para controlar el envío de datos a MongoDB

# Configuración de UART para el sensor y GPS
uart_sensor = UART(0, baudrate=4800, tx=Pin(0), rx=Pin(1))
modulo_gps = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

# Inicialización de la librería GPS
Zona_Horaria = -5
gps = MicropyGPS(Zona_Horaria)

# Comando de consulta Modbus para el sensor
queryData = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x07, 0x04, 0x08])

# Inicializar el temporizador
timer = Timer()
captura_activa = False  # Variable de estado para controlar si la captura está activa
server_socket = None
# URL y API Key de MongoDB
MONGO_API_URL = "https://us-east-1.aws.data.mongodb-api.com/app/data-sunbmfa/endpoint/data/v1/action/insertOne"
API_KEY = "gAHxYHCabWMfvLHv8mfqZZegivGT71xXZk4WcWNlodadKZImP6r2K94uvUeqYHW2"


# Función para calcular el CRC16
def crc16(data: bytes):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if (crc & 0x0001):
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    crc_bytes = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    print(f"CRC16 calculado para {data.hex()}: {crc_bytes.hex()}")
    return crc_bytes

# Convertir un valor flotante a 4 bytes en formato IEEE 754 (big endian)
def convertir_factor_a_bytes(factor_a):
    bytes_result = struct.pack('>f', factor_a)
    print(f"Factor {factor_a} convertido a IEEE 754 (big endian): {bytes_result.hex()}")
    return bytes_result

# Función para enviar comandos Modbus al sensor
def write_register_with_crc(command_with_crc):
    uart_sensor.write(command_with_crc)
    time.sleep(0.02)
    print("recepcion habilitada")
    time.sleep(0.6)
    if uart_sensor.any():
        response = uart_sensor.read(8)
        print(f"Respuesta del sensor: {response.hex()}")

# Función para calibrar el sensor
# Función para calibrar el sensor
def calibrar_sensor(factor_a_nitrogeno=None, offset_nitrogeno=None, factor_a_fosforo=None, offset_fosforo=None, factor_a_potasio=None, offset_potasio=None):
    # Comandos Modbus para cada variable si los valores están presentes
    if factor_a_nitrogeno is not None:
        print(f"Calibrando Factor A de Nitrógeno: {factor_a_nitrogeno}")
        factor_a_nitrogeno_bytes = convertir_factor_a_bytes(factor_a_nitrogeno)
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xE8]) + factor_a_nitrogeno_bytes[:2] + crc16(bytes([0x01, 0x06, 0x04, 0xE8]) + factor_a_nitrogeno_bytes[:2]))
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xE9]) + factor_a_nitrogeno_bytes[2:] + crc16(bytes([0x01, 0x06, 0x04, 0xE9]) + factor_a_nitrogeno_bytes[2:]))
    if offset_nitrogeno is not None:
        print(f"Calibrando Offset de Nitrógeno: {offset_nitrogeno}")
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xEA, offset_nitrogeno >> 8, offset_nitrogeno & 0xFF]) + crc16(bytes([0x01, 0x06, 0x04, 0xEA, offset_nitrogeno >> 8, offset_nitrogeno & 0xFF])))

    if factor_a_fosforo is not None:
        print(f"Calibrando Factor A de Fósforo: {factor_a_fosforo}")
        factor_a_fosforo_bytes = convertir_factor_a_bytes(factor_a_fosforo)
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xF2]) + factor_a_fosforo_bytes[:2] + crc16(bytes([0x01, 0x06, 0x04, 0xF2]) + factor_a_fosforo_bytes[:2]))
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xF3]) + factor_a_fosforo_bytes[2:] + crc16(bytes([0x01, 0x06, 0x04, 0xF3]) + factor_a_fosforo_bytes[2:]))
    if offset_fosforo is not None:
        print(f"Calibrando Offset de Fósforo: {offset_fosforo}")
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xF4, offset_fosforo >> 8, offset_fosforo & 0xFF]) + crc16(bytes([0x01, 0x06, 0x04, 0xF4, offset_fosforo >> 8, offset_fosforo & 0xFF])))

    if factor_a_potasio is not None:
        print(f"Calibrando Factor A de Potasio: {factor_a_potasio}")
        factor_a_potasio_bytes = convertir_factor_a_bytes(factor_a_potasio)
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xFC]) + factor_a_potasio_bytes[:2] + crc16(bytes([0x01, 0x06, 0x04, 0xFC]) + factor_a_potasio_bytes[:2]))
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xFD]) + factor_a_potasio_bytes[2:] + crc16(bytes([0x01, 0x06, 0x04, 0xFD]) + factor_a_potasio_bytes[2:]))
    if offset_potasio is not None:
        print(f"Calibrando Offset de Potasio: {offset_potasio}")
        write_register_with_crc(bytes([0x01, 0x06, 0x04, 0xFE, offset_potasio >> 8, offset_potasio & 0xFF]) + crc16(bytes([0x01, 0x06, 0x04, 0xFE, offset_potasio >> 8, offset_potasio & 0xFF])))



# Verificar si un archivo existe
def archivo_existe(nombre_archivo):
    try:
        uos.stat(nombre_archivo)
        return True
    except OSError:
        return False

# Verificar si el archivo CSV existe
def verificar_archivo_csv():
    if not archivo_existe(archivo_csv):
        with open(archivo_csv, "w") as archivo:
            archivo.write("Fecha,Hora,Latitud,Longitud,Humedad,Temperatura,Conductividad,pH,Nitrógeno,Fósforo,Potasio\n")

# Verificar si el archivo de credenciales existe
def verificar_archivo_wifi():
    if not archivo_existe(archivo_wifi):
        with open(archivo_wifi, "w") as archivo:
            archivo.write("")  # Crear archivo vacío si no existe

# Guardar credenciales Wi-Fi
def guardar_credenciales_wifi(ssid, password):
    with open(archivo_wifi, "a") as archivo:
        archivo.write(f"SSID: {ssid}, Password: {password}\n")
        
        
# Función para editar credenciales Wi-Fi
def editar_credenciales_wifi(ssid, new_password):
    if archivo_existe(archivo_wifi):
        with open(archivo_wifi, "r") as archivo:
            lineas = archivo.readlines()
        with open(archivo_wifi, "w") as archivo:
            for linea in lineas:
                if f"SSID: {ssid}," in linea:
                    archivo.write(f"SSID: {ssid}, Password: {new_password}\n")
                else:
                    archivo.write(linea)

def decode_url_encoded(text):
    replacements = {
        '%20': ' ',  # Espacio
        '%3F': '?',  # Signo de interrogación
        '%26': '&',  # Ampersand
        '%23': '#',  # Numeral
        '%25': '%',  # Porcentaje
        '%2F': '/',  # Barra
        '%3A': ':',  # Dos puntos
        '%2C': ',',  # Coma
        '%3D': '=',  # Igual
        '%40': '@',  # Arroba
        '%2B': '+',  # Más
        '%2D': '-',  # Guion
        '%5F': '_',  # Guion bajo
        '%2E': '.',  # Punto
    }
    
    for encoded, decoded in replacements.items():
        text = text.replace(encoded, decoded)
    return text


# Función para conectar a Wi-Fi usando las credenciales guardadas con límite de tiempo
def conectar_wifi(ssid, password, tiempo_limite=10):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    
    print(f"Conectando a la red Wi-Fi {ssid}...")

    tiempo_inicio = time.time()  # Iniciar temporizador
    while not wlan.isconnected():
        if time.time() - tiempo_inicio > tiempo_limite:  # Verificar si se excedió el tiempo límite
            print(f"No se pudo conectar a {ssid} en el tiempo límite de {tiempo_limite} segundos.")
            wlan.active(False)  # Desactivar el Wi-Fi si no se logra la conexión
            return False
        time.sleep(1)  # Pausa de 1 segundo para no sobrecargar el ciclo
    
    print(f"Conectado con IP: {wlan.ifconfig()[0]}")
    return True

# Función para borrar los archivos CSV y de índice
def borrar_archivos():
    try:
        # Borrar archivo CSV
        if archivo_existe(archivo_csv):
            uos.remove(archivo_csv)
            print(f"Archivo {archivo_csv} eliminado.")
        
        # Borrar archivo del último índice
        if archivo_existe(archivo_indice):
            uos.remove(archivo_indice)
            print(f"Archivo {archivo_indice} eliminado.")

        # Crear de nuevo el archivo CSV con las cabeceras
        verificar_archivo_csv()
        print(f"Archivo {archivo_csv} creado de nuevo con cabeceras.")

        return True
    except Exception as e:
        print(f"Error al borrar los archivos: {e}")
        return False


# Función para apagar el AP y cerrar el servidor
def apagar_punto_de_acceso(ap):
    global server_socket
    if ap.active():
        ap.active(False)
        print("Punto de acceso apagado.")
        
#         # Si el servidor está activo, cerrarlo
#         if server_socket:
#             server_socket.close()
#             print("Servidor cerrado.")
#             server_socket = None  # Resetear la variable para indicar que el servidor está cerrado
#             
#             # Agregar un pequeño retraso para asegurarse de que el puerto se libera
#             time.sleep(1)
            
        gc.collect()


# Apagar Wi-Fi en modo cliente
def apagar_wifi_cliente():
    wlan = network.WLAN(network.STA_IF)
    if wlan.active():
        wlan.active(False)
        print("Wi-Fi cliente apagado.")


# Función para activar el AP
def activar_punto_de_acceso(ap):
    global server_socket
    
    # Apagar el Wi-Fi en modo cliente antes de activar el AP
    apagar_wifi_cliente()
    
    if not ap.active():
        ap.active(True)
        print("Punto de acceso activado.")
        
        # Verificar si el servidor está activo
        if server_socket is None:
            print("Reiniciando el servidor web...")
            try:
                time.sleep(1)  # Espera un momento para asegurarte de que el puerto esté libre
                iniciar_servidor_web()  # Reiniciar el servidor web
                print("Servidor web reiniciado correctamente.")
            except Exception as e:
                print(f"Error al reiniciar el servidor web: {e}")
        else:
            print("El servidor web ya estaba activo.")
        
        gc.collect()

# Escanear redes y conectarse a la primera con acceso a internet
def escanear_y_conectar_redes(tiempo_limite_por_red=10):
    global ap  # Asegurarnos de que estamos usando la variable ap para controlar el AP
    apagar_punto_de_acceso(ap)  # Apagar el AP antes de intentar conectarse a Wi-Fi

    with open(archivo_wifi, "r") as archivo:
        lineas = archivo.read().splitlines()
        conexion_exitosa = False  # Variable para rastrear si se conectó a alguna red
        
        for linea in lineas:
            # Separar SSID y Password basados en el formato
            if "SSID" in linea and "Password" in linea:
                ssid = linea.split(",")[0].split(": ")[1].strip()
                password = linea.split(",")[1].split(": ")[1].strip()
                
                print(f"Intentando conectar a la red SSID: {ssid}, con clave: {password}")

                # Intentar conectar con un tiempo límite
                if conectar_wifi(ssid, password, tiempo_limite=tiempo_limite_por_red):
                    print(f"Conectado a {ssid}.")
                    conexion_exitosa = True  # Marcar como exitosa
                    break  # Salir del ciclo si se conecta con éxito
                else:
                    print(f"No se pudo conectar a {ssid}, intentando con la siguiente red.")
    
    if not conexion_exitosa:
        print("No se pudo conectar a ninguna red. Reactivando el AP...")
        activar_punto_de_acceso(ap)  # Volver a activar el AP si no se logra la conexión
    
    return conexion_exitosa  # Devuelve True si la conexión fue exitosa, de lo contrario False


def enviar_datos_a_mongodb(fecha, hora, latitud, longitud, sensor_data):
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'api-key': API_KEY
    }

    # Crear el payload con los campos validados
    payload = {
        "collection": "picow",
        "database": "TelematicaB",
        "dataSource": "TelematicaB",
        "document": {
            "Fecha": fecha,
            "Hora": hora,
            "Latitud": float(latitud),  # Asegurar que sea número
            "Longitud": float(longitud),  # Asegurar que sea número
            "Humedad": sensor_data['Humedad'],
            "Temperatura": sensor_data['Temperatura'],
            "Conductividad": sensor_data['Conductividad'],
            "pH": sensor_data['pH'],
            "Nitrogeno": sensor_data['Nitrógeno'],  # Valor validado de Nitrógeno
            "Fosforo": sensor_data['Fósforo'],      # Valor validado de Fósforo
            "Potasio": sensor_data['Potasio']       # Valor validado de Potasio
        }
    }

    # Mostrar el payload y su tamaño antes de enviarlo
    print("Enviando el siguiente payload a MongoDB:")
    print(ujson.dumps(payload))  # Mostrar el JSON con formato
    print("Tamaño del payload:", len(ujson.dumps(payload)))

    try:
        # Enviar los datos a MongoDB
        response = requests.post(MONGO_API_URL, headers=headers, data=json.dumps(payload))
        print("Respuesta completa del servidor:", response.text)
        if response.status_code == 201:
            print("Datos enviados a MongoDB correctamente.")
            return True
        else:
            print(f"Error al enviar datos. Código de estado: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error al enviar los datos a MongoDB: {e}")
        return False

# Subir datos del CSV empezando desde el último índice
# Subir datos del CSV empezando desde el último índice
def subir_datos_csv():
    ultimo_indice = obtener_ultimo_indice()

    if archivo_existe(archivo_csv):
        with open(archivo_csv, "r") as archivo:
            lineas = archivo.readlines()[1:]  # Omitir las cabeceras

        for indice, linea in enumerate(lineas[ultimo_indice:], start=ultimo_indice):
            fila = linea.strip().split(',')
            fecha = fila[0]
            hora = fila[1]
            latitud = fila[2]
            longitud = fila[3]

            sensor_data = {
                "Humedad": float(fila[4]),
                "Temperatura": float(fila[5]),
                "Conductividad": int(fila[6]),
                "pH": float(fila[7]),
                "Nitrógeno": float(fila[8]),
                "Fósforo": float(fila[9]),
                "Potasio": float(fila[10])
            }

            if enviar_datos_a_mongodb(fecha, hora, latitud, longitud, sensor_data):
                guardar_ultimo_indice(indice + 1)
                gc.collect()  # Liberar memoria
            else:
                print("Error al subir los datos, deteniendo el proceso.")
                break  # Detener si hay un error al subir

    # Aquí se hace el reinicio cuando todos los datos han sido enviados
    print("Todos los datos han sido enviados, reiniciando la Raspberry Pi Pico W...")
    time.sleep(2)  # Espera 2 segundos para mostrar el mensaje en consola
    machine.reset()  # Reinicia la Raspberry Pi Pico W

# Guardar el último índice subido a MongoDB
def guardar_ultimo_indice(indice):
    with open(archivo_indice, "w") as archivo:
        archivo.write(str(indice))

# Obtener el último índice subido a MongoDB
def obtener_ultimo_indice():
    try:
        with open(archivo_indice, "r") as archivo:
            return int(archivo.read().strip())
    except:
        return 0

def todos_los_datos_subidos():
    if not archivo_existe(archivo_csv):
        return False

    with open(archivo_csv, "r") as archivo:
        lineas = archivo.readlines()

    total_lineas_csv = len(lineas) - 1  # Restar la cabecera
    indice_guardado = obtener_ultimo_indice()

    return indice_guardado >= total_lineas_csv
# Función para leer datos del sensor
def read_sensor():
    print("Transmisión habilitada, enviando datos al sensor")
    uart_sensor.write(queryData)
    time.sleep(0.02)
    print("Recepción habilitada")
    time.sleep(0.6)
    response = uart_sensor.read(19)
    if response and len(response) == 19:
        humidity = (response[3] << 8 | response[4]) / 10.0
        temperature = (response[5] << 8 | response[6]) / 10.0
        conductivity = response[7] << 8 | response[8]
        ph = (response[9] << 8 | response[10]) / 10.0
        nitrogen_raw = (response[11] << 8 | response[12])
        phosphorus_raw = (response[13] << 8 | response[14])
        potassium_raw = (response[15] << 8 | response[16])
        
        nitrogen = max(0, 0.005 * nitrogen_raw)
        phosphorus = max(0, 0.0364 * phosphorus_raw)
        potassium = max(0, 0.4774 * potassium_raw)

        return {
            "Humedad": humidity,
            "Temperatura": temperature,
            "Conductividad": conductivity,
            "pH": ph,
            "Nitrógeno": nitrogen,
            "Fósforo": phosphorus,
            "Potasio": potassium
        }
    else:
        print("Error al leer los datos o respuesta invalida.")
    return None

# Función para leer datos del GPS
def get_gps_data():
    largo = modulo_gps.any()
    if largo > 0:
        b = modulo_gps.read(largo)
        for x in b:
            gps.update(chr(x))

    latitud = convertir(gps.latitude)
    longitud = convertir(gps.longitude)
    
    print(f"Latitud: {latitud}, Longitud: {longitud}")
    print('Date:', gps.date_string('s_dmy'))
    if latitud is None or longitud is None:
        return {"error": "Esperando el fix del GPS..."}

    t = gps.timestamp
    horario = '{:02d}:{:02d}:{:02d}'.format(t[0], t[1], int(t[2]))
    fecha = gps.date_string('s_dmy')
    return {
        "Fecha": fecha,
        "Hora": horario,
        "Latitud": latitud,
        "Longitud": longitud
    }

# Función para convertir los datos del GPS en formato adecuado
def convertir(secciones):
    if secciones[0] == 0:
        return None
    data = secciones[0] + (secciones[1] / 60.0)
    if secciones[2] == 'S':
        data = -data
    if secciones[2] == 'W':
        data = -data

    return '{0:.6f}'.format(data)

# Función para manejar la captura continua de datos
def manejar_captura(timer):
    print("Capturando datos del sensor y GPS...")
    
    # Leer datos del sensor
    sensor_data = read_sensor()
    if sensor_data:
        print(f"Datos del sensor obtenidos: {sensor_data}")
        
        # Leer datos del GPS
        gps_data = get_gps_data()
        if gps_data and "error" not in gps_data:
            print(f"Datos del GPS obtenidos: {gps_data}")
            
            # Guardar en CSV si ambos datos se obtienen correctamente
            print("Guardando datos en CSV...")
            guardar_datos_csv(gps_data["Fecha"], gps_data["Hora"], gps_data["Latitud"], gps_data["Longitud"], sensor_data)
            print("Datos guardados exitosamente.")
        else:
            print("Error obteniendo datos del GPS.")
    else:
        print("Error obteniendo datos del sensor.")

# Guardar datos en CSV
def guardar_datos_csv(fecha, hora, latitud, longitud, sensor_data):
    with open(archivo_csv, "a") as archivo:
        archivo.write(f"{fecha},{hora},{latitud},{longitud},{sensor_data['Humedad']},{sensor_data['Temperatura']},")
        archivo.write(f"{sensor_data['Conductividad']},{sensor_data['pH']},{sensor_data['Nitrógeno']},")
        archivo.write(f"{sensor_data['Fósforo']},{sensor_data['Potasio']}\n")

# Función para iniciar el punto de acceso
def iniciar_punto_de_acceso():
    ap = network.WLAN(network.AP_IF)
    ap.config(essid="PicoW_Setup", password="12345678")
    ap.active(True)
    print("Punto de acceso iniciado. Conéctese a la red 'PicoW_Setup' con la contraseña '12345678'.")
    print("Dirección IP del punto de acceso:", ap.ifconfig()[0])
    return ap

def actualizar_codigo_desde_github():
    url = "https://raw.githubusercontent.com/CamilowBaldovino/RASPBERRY-PICO-W/main/main.py"
    print("Descargando:", url)

    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open("main.py", "w") as f:  # Sobrescribe main.py
                f.write(response.text)
            print("Archivo main.py actualizado correctamente.")
        else:
            print("Error al descargar. Codigo HTTP:", response.status_code)
        response.close()
    except Exception as e:
        print("Error al descargar archivo:", e)

# Función para manejar las solicitudes HTTP
def iniciar_servidor_web():
    global server_socket, captura_activa
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    server_socket = socket.socket()
    server_socket.bind(addr)
    server_socket.listen(1)

    html_form = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control de Sensores y Wi-Fi</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f9;
            color: #333;
            margin: 0;
            padding: 0;
        }
        h2 {
            color: #4CAF50;
        }
        .container {
            width: 80%;
            max-width: 1000px;
            margin: 20px auto;
            padding: 20px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        button, input[type="submit"] {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            margin: 10px 0;
            font-size: 16px;
            border-radius: 5px;
            cursor: pointer;
        }
        button:hover, input[type="submit"]:hover {
            background-color: #45a049;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 8px;
            margin: 5px 0 15px;
            border-radius: 5px;
            border: 1px solid #ddd;
        }
        form {
            margin: 20px 0;
        }
        .status-message {
            padding: 10px;
            margin-top: 15px;
            border-radius: 5px;
            background-color: #f8f8f8;
            font-size: 16px;
        }
        .status-message.success {
            background-color: #d4edda;
            color: #155724;
        }
        .status-message.error {
            background-color: #f8d7da;
            color: #721c24;
        }
        #sensor, #gps {
            padding: 10px;
            margin-top: 10px;
            border-radius: 5px;
            background-color: #e9ecef;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Control de Sensores</h2>
        <button onclick="iniciarCaptura()">Iniciar Captura de datos de la muestra</button>
        <button onclick="detenerCaptura()">Detener Captura de datos de la muestra</button>
        

        <h2>Datos del Sensor</h2>
        <div id="sensor">Esperando datos del sensor...</div>
        <button onclick="subirDatos()">Subir Datos a la nube</button>
        <p id="estadoSubida" class="status-message"></p>
        
        <h2>Actualizacion de software</h2>
        <button onclick="actualizarCodigo()">Actualizar Codigo</button>

        
        <h2>Agregar Credenciales Wi-Fi</h2>
        <form action="/guardar_wifi" method="post">
            <label for="ssid">SSID:</label>
            <input type="text" name="ssid" id="ssid"><br>
            <label for="password">Contraseña:</label>
            <input type="password" name="password" id="password"><br><br>
            <input type="submit" value="Guardar Credenciales">
        </form>

        <h2>Editar Credenciales Wi-Fi</h2>
        <form action="/editar_wifi" method="post">
            <label for="ssid_edit">SSID:</label>
            <input type="text" name="ssid" id="ssid_edit"><br>
            <label for="new_password">Nueva Contraseña:</label>
            <input type="password" name="new_password" id="new_password"><br><br>
            <input type="submit" value="Editar Credenciales">
        </form>

        <h2>Calibración del Sensor</h2>
        <form action="/calibrar_sensor" method="post">
            <h3>Nitrógeno</h3>
            <label for="factor_a_nitrogeno">Factor A:</label>
            <input type="text" name="factor_a_nitrogeno" id="factor_a_nitrogeno"><br>
            <label for="offset_nitrogeno">Offset:</label>
            <input type="text" name="offset_nitrogeno" id="offset_nitrogeno"><br>

            <h3>Fósforo</h3>
            <label for="factor_a_fosforo">Factor A:</label>
            <input type="text" name="factor_a_fosforo" id="factor_a_fosforo"><br>
            <label for="offset_fosforo">Offset:</label>
            <input type="text" name="offset_fosforo" id="offset_fosforo"><br>

            <h3>Potasio</h3>
            <label for="factor_a_potasio">Factor A:</label>
            <input type="text" name="factor_a_potasio" id="factor_a_potasio"><br>
            <label for="offset_potasio">Offset:</label>
            <input type="text" name="offset_potasio" id="offset_potasio"><br><br>

            <input type="submit" value="Calibrar Sensor">
        </form>

        <h2>Borrar Archivos CSV e Índice</h2>
        <button onclick="borrarArchivos()">Borrar Archivos</button>

        <div class="status-message" id="statusMessage"></div>

        <script>
            function iniciarCaptura() {
                fetch('/iniciar_captura', { method: 'POST' })
                .then(response => response.json())
                .then(data => { 
                    alert(data.message); 
                });
            }
            
            function detenerCaptura() {
                fetch('/detener_captura', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                });
            }

            function subirDatos() {
                const status = document.getElementById('statusMessage');
                status.className = "status-message";
                status.textContent = "Subiendo datos...";
                fetch('/subir', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    status.className = "status-message success";
                    status.textContent = data.message;
                })
                .catch(error => {
                    status.className = "status-message error";
                    status.textContent = "Error al subir los datos.";
                });
            }

            function borrarArchivos() {
                fetch('/borrar_archivos', { method: 'POST' })
                .then(response => response.json())
                .then(data => { 
                    alert(data.message); 
                });
            }
            
            function actualizarCodigo() {
                const status = document.getElementById('statusMessage');
                status.className = "status-message";
                status.textContent = "Buscando actualizaciones...";
                fetch('/actualizar', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    status.className = "status-message success";
                    status.textContent = data.message;
                })
                .catch(error => {
                    status.className = "status-message error";
                    status.textContent = "Error al actualizar el codigo.";
                });
            }            
            
            function verificarEstadoSubida() {
                fetch('/estado_subida')
                .then(response => response.json())
                .then(data => {
                    const estado = document.getElementById('estadoSubida');
                    if (data.subido) {
                        estado.className = "status-message success";
                        estado.textContent = "Todos los datos han sido subidos.";
                    } else {
                        estado.className = "status-message error";
                        estado.textContent = "Quedan datos pendientes por subir.";
                    }
                })
                .catch(error => {
                    console.error("Error consultando estado de subida:", error);
                });
            }
             
            const unidades = {
                "Temperatura": "C",
                "Humedad": "%",
                "Nitrógeno": "mg/kg",
                "Fósforo": "mg/kg",
                "Potasio": "mg/kg",
                "Conductividad": "us/cm",
                "pH": ""
            };

            setInterval(function() {
                fetch('/datos')
                .then(response => response.json())
                .then(data => {
                    let sensorContent = "";
                    if (data.sensor && !data.sensor.error) {
                        for (const [key, value] of Object.entries(data.sensor)) {
                            const unidad = unidades[key] || "";
                            sensorContent += key + ": " + value + " " + unidad + "<br>";
                        }
                    } else {
                        sensorContent += "No se pudieron obtener datos del sensor.";
                    }
                    document.getElementById('sensor').innerHTML = sensorContent;
                });
            }, 5000);
            window.onload = function() {
                verificarEstadoSubida();
            };
        </script>
    </div>
</body>
</html>"""

    while True:
        try:
            cl, addr = server_socket.accept()
            request = cl.recv(1024).decode('utf-8')

            if "GET / " in request:
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n')
                cl.sendall(html_form)
                
            elif "GET /estado_subida" in request:
                estado = todos_los_datos_subidos()
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"subido": estado}))
                

            elif "POST /guardar_wifi" in request:
                body_start = request.find('\r\n\r\n') + 4
                body = request[body_start:]
                body = decode_url_encoded(body)  # Decodifica los caracteres URL-encoded
                ssid = body.split('ssid=')[1].split('&')[0]
                password = body.split('password=')[1]
                guardar_credenciales_wifi(ssid, password)
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"message": "Credenciales guardadas"}))

            elif "POST /editar_wifi" in request:
                body_start = request.find('\r\n\r\n') + 4
                body = request[body_start:]
                body = decode_url_encoded(body)  # Decodifica los caracteres URL-encoded
                ssid = body.split('ssid=')[1].split('&')[0]
                new_password = body.split('new_password=')[1]
                editar_credenciales_wifi(ssid, new_password)
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"message": "Credenciales editadas correctamente"}))

            elif "POST /calibrar_sensor" in request:
                body_start = request.find('\r\n\r\n') + 4
                body = request[body_start:]
                params = {k: v for k, v in (item.split('=') for item in body.split('&') if '=' in item)}
                factor_a_nitrogeno = float(params["factor_a_nitrogeno"]) if "factor_a_nitrogeno" in params and params["factor_a_nitrogeno"] else None
                offset_nitrogeno = int(params["offset_nitrogeno"]) if "offset_nitrogeno" in params and params["offset_nitrogeno"] else None
                factor_a_fosforo = float(params["factor_a_fosforo"]) if "factor_a_fosforo" in params and params["factor_a_fosforo"] else None                
                offset_fosforo = int(params["offset_fosforo"]) if "offset_fosforo" in params and params["offset_fosforo"] else None
                factor_a_potasio = float(params["factor_a_potasio"]) if "factor_a_potasio" in params and params["factor_a_potasio"] else None
                offset_potasio = int(params["offset_potasio"]) if "offset_potasio" in params and params["offset_potasio"] else None

                calibrar_sensor(
                    factor_a_nitrogeno=factor_a_nitrogeno,
                    offset_nitrogeno=offset_nitrogeno,
                    factor_a_fosforo=factor_a_fosforo,
                    offset_fosforo=offset_fosforo,
                    factor_a_potasio=factor_a_potasio,
                    offset_potasio=offset_potasio
                )
                
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"message": "Calibración enviada al sensor correctamente"}).encode())

            elif "POST /iniciar_captura" in request:
                if not captura_activa:
                    timer.init(period=1500, mode=Timer.PERIODIC, callback=manejar_captura)
                    captura_activa = True
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"message": "Captura iniciada"}))
                
            elif "POST /detener_captura" in request:
                if captura_activa:
                    timer.deinit()
                    captura_activa = False
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"message": "Captura detenida"}))
                
            
            elif "POST /subir" in request:
                if escanear_y_conectar_redes():
                    subir_datos_csv()
                else:
                    cl.send('HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n')
                    cl.send(ujson.dumps({"message": "No se pudo conectar a una red Wi-Fi"}))
                    
            elif "POST /actualizar" in request:
                if escanear_y_conectar_redes():
                    try:
                        actualizar_codigo_desde_github()
                        cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                        cl.send(ujson.dumps({"message": "Codigo actualizado. Reiniciando..."}))
                        time.sleep(2)
                        machine.reset()
                    except Exception as e:
                        cl.send('HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n')
                        cl.send(ujson.dumps({"message": f"Error al actualizar: {str(e)}"}))
                else:
                    cl.send('HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n')
                    cl.send(ujson.dumps({"message": "No se pudo conectar a una red Wi-Fi"}))


            elif "POST /borrar_archivos" in request:
                if borrar_archivos():
                    cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                    cl.send(ujson.dumps({"message": "Archivos borrados y CSV recreado"}))
                else:
                    cl.send('HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n')
                    cl.send(ujson.dumps({"message": "Error al borrar los archivos"}))

            elif "GET /datos" in request:
                sensor_data = read_sensor()
                gps_data = get_gps_data()
                data = {
                    "sensor": sensor_data if sensor_data else {"error": "No se pudieron obtener datos del sensor"},
                    "gps": gps_data
                }
                cl.send('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n')
                cl.send(ujson.dumps(data))

            cl.close()
        except OSError as e:
            print(f"Error en el servidor: {e}")
            if server_socket:
                print("Cerrando socket")
                server_socket.close()
            server_socket = None
            time.sleep(1)
            iniciar_servidor_web()
            break


# Iniciar el AP y servidor
ap = iniciar_punto_de_acceso()
verificar_archivo_csv()
verificar_archivo_wifi()
iniciar_servidor_web()



