import os
import re
import subprocess
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
TIPOS_VIDEO = [("Video", "*.mp4 *.mov *.mkv *.avi"), ("Todos", "*.*")]
SIN_VIDEO = "Ningún video seleccionado"


def a_segundos(texto):
    """Acepta '508', '8:28' o '1:08:28'."""
    total = 0.0
    for p in texto.strip().split(":"):
        total = total * 60 + float(p)
    return total


def tiene_stream(ruta, tipo):
    """tipo: 'v:0' para video, 'a:0' para audio."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", tipo,
         "-show_entries", "stream=codec_type",
         "-of", "default=nw=1:nk=1", ruta],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    return bool(r.stdout.strip())


def duracion(ruta):
    # Intentos 1 y 2: metadatos del contenedor y del stream de video
    for entrada in ("format=duration", "stream=duration"):
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", entrada, "-of", "default=nw=1:nk=1", ruta],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        for token in r.stdout.split():
            try:
                valor = float(token)
                if valor > 0:
                    return valor
            except ValueError:
                pass

    # Intento 3: recorrer el archivo sin recodificar y leer el último time=
    r = subprocess.run(
        ["ffmpeg", "-i", ruta, "-c", "copy", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
        creationflags=NO_WINDOW)
    tiempos = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", r.stderr)
    if tiempos:
        h, m, s = tiempos[-1]
        return int(h) * 3600 + int(m) * 60 + float(s)

    raise RuntimeError("No pude determinar la duración. ffmpeg dijo: " + r.stderr[-400:])


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Cortador de series para TikTok")
        self.geometry("640x800")
        self.rutas = {"dividir": None, "quitar": None}
        self.etiquetas = {}
        self.campos = {}

        tabs = ctk.CTkTabview(self, height=370)
        tabs.pack(fill="x", padx=15, pady=(12, 6))
        tab1 = tabs.add("Dividir en capítulos")
        tab2 = tabs.add("Quitar tramo")

        # ---- Pestaña 1: dividir ----
        self.selector(tab1, "dividir")
        self.campo(tab1, "cortes", "Puntos de corte (ej: 8:28, 16:56)", "")
        self.campo(tab1, "partes", "Partes iguales (si dejas cortes vacío)", "3")
        self.campo(tab1, "solape", "Solape en capítulos 2+ (seg)", "2")
        self.campo(tab1, "fade_in", "Fade in (seg)", "0.5")
        self.campo(tab1, "fade_out", "Fade out (seg)", "0.8")
        self.campo(tab1, "crf", "Calidad CRF (16-20, menor = mejor)", "17")
        b1 = ctk.CTkButton(tab1, text="Exportar capítulos", command=self.clic_dividir)
        b1.pack(pady=12)

        # ---- Pestaña 2: quitar tramo ----
        self.selector(tab2, "quitar")
        self.campo(tab2, "q_ini", "Inicio del tramo a quitar (ej: 2:10)", "")
        self.campo(tab2, "q_fin", "Fin del tramo a quitar (ej: 3:45)", "")
        self.campo(tab2, "q_fade", "Fundido en la unión (seg, 0 = corte seco)", "0.3")
        self.campo(tab2, "q_crf", "Calidad CRF (16-20, menor = mejor)", "17")
        b2 = ctk.CTkButton(tab2, text="Quitar tramo y unir", command=self.clic_quitar)
        b2.pack(pady=12)

        # ---- Zona común: barra, log y limpiar ----
        self.barra = ctk.CTkProgressBar(self, width=540)
        self.barra.set(0)
        self.barra.pack(pady=(6, 0))
        self.log = ctk.CTkTextbox(self, width=590, height=170)
        self.log.pack(pady=10)
        self.btn_limpiar = ctk.CTkButton(
            self, text="Limpiar todo", fg_color="gray30", command=self.limpiar)
        self.btn_limpiar.pack(pady=(0, 10))

        self.botones = [b1, b2, self.btn_limpiar]

    # ---------- construcción de la interfaz ----------
    def selector(self, padre, clave):
        ctk.CTkButton(padre, text="Elegir video",
                      command=lambda: self.elegir(clave)).pack(pady=(8, 4))
        etiqueta = ctk.CTkLabel(padre, text=SIN_VIDEO)
        etiqueta.pack(pady=(0, 8))
        self.etiquetas[clave] = etiqueta

    def campo(self, padre, clave, etiqueta, defecto):
        fila = ctk.CTkFrame(padre, fg_color="transparent")
        fila.pack(fill="x", padx=15, pady=3)
        ctk.CTkLabel(fila, text=etiqueta, width=290, anchor="w").pack(side="left")
        e = ctk.CTkEntry(fila, width=200)
        e.insert(0, defecto)
        e.pack(side="right")
        self.campos[clave] = e

    # ---------- acciones de la interfaz ----------
    def elegir(self, clave):
        ruta = filedialog.askopenfilename(filetypes=TIPOS_VIDEO)
        if ruta:
            self.rutas[clave] = ruta
            self.etiquetas[clave].configure(text=os.path.basename(ruta))

    def limpiar(self):
        self.log.delete("1.0", "end")
        self.barra.set(0)
        for clave in self.rutas:
            self.rutas[clave] = None
            self.etiquetas[clave].configure(text=SIN_VIDEO)
        for clave in ("cortes", "q_ini", "q_fin"):
            self.campos[clave].delete(0, "end")

    def escribir(self, txt):
        self.after(0, lambda: (self.log.insert("end", txt + "\n"), self.log.see("end")))

    def bloquear(self, estado):
        for b in self.botones:
            b.configure(state=estado)

    def lanzar(self, tarea):
        """Ejecuta 'tarea' en un hilo aparte para no congelar la ventana."""
        self.bloquear("disabled")

        def trabajo():
            try:
                tarea()
            except subprocess.CalledProcessError as e:
                self.escribir("Error de FFmpeg: " + (e.stderr or str(e))[-500:])
            except Exception as e:
                self.escribir(f"Error: {e}")
            finally:
                self.after(0, lambda: self.bloquear("normal"))

        threading.Thread(target=trabajo, daemon=True).start()

    # ---------- botón: dividir ----------
    def clic_dividir(self):
        ruta = self.rutas["dividir"]
        if not ruta:
            messagebox.showwarning("Falta el video", "Elige un video primero.")
            return
        # Leemos los campos AQUÍ (hilo principal), no dentro del hilo de trabajo
        c = {k: self.campos[k].get().strip()
             for k in ("cortes", "partes", "solape", "fade_in", "fade_out", "crf")}
        self.lanzar(lambda: self.dividir(ruta, c))

    def dividir(self, ruta, c):
        if not tiene_stream(ruta, "v:0"):
            raise RuntimeError("Este archivo no contiene video. Revisa que sea un video real.")

        solape, fin_in, fin_out = float(c["solape"]), float(c["fade_in"]), float(c["fade_out"])
        total = duracion(ruta)

        if c["cortes"]:
            cortes = sorted(a_segundos(t) for t in c["cortes"].split(","))
        else:
            n = int(c["partes"])
            cortes = [total / n * i for i in range(1, n)]

        limites = [0] + cortes + [total]
        base, _ = os.path.splitext(ruta)
        n_partes = len(limites) - 1
        self.after(0, lambda: self.barra.set(0))

        for i in range(n_partes):
            inicio = max(0, limites[i] - (solape if i > 0 else 0))
            dur = limites[i + 1] - inicio
            salida = f"{base}_parte{i + 1}.mp4"

            vf = (f"fade=t=in:st=0:d={fin_in},"
                  f"fade=t=out:st={dur - fin_out}:d={fin_out}")
            af = (f"afade=t=in:st=0:d={fin_in},"
                  f"afade=t=out:st={dur - fin_out}:d={fin_out}")

            self.escribir(f"Exportando parte {i + 1}/{n_partes} ({dur / 60:.1f} min)...")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(inicio), "-i", ruta, "-t", str(dur),
                 "-vf", vf, "-af", af,
                 "-c:v", "libx264", "-crf", c["crf"], "-preset", "slow",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", salida],
                check=True, capture_output=True, text=True, errors="replace",
                creationflags=NO_WINDOW)
            self.after(0, lambda v=(i + 1) / n_partes: self.barra.set(v))
            self.escribir(f"  OK -> {os.path.basename(salida)}")

        self.escribir("Listo.")

    # ---------- botón: quitar tramo ----------
    def clic_quitar(self):
        ruta = self.rutas["quitar"]
        if not ruta:
            messagebox.showwarning("Falta el video", "Elige un video primero.")
            return
        c = {k: self.campos[k].get().strip()
             for k in ("q_ini", "q_fin", "q_fade", "q_crf")}
        self.lanzar(lambda: self.quitar(ruta, c))

    def quitar(self, ruta, c):
        if not tiene_stream(ruta, "v:0"):
            raise RuntimeError("Este archivo no contiene video.")
        if not tiene_stream(ruta, "a:0"):
            raise RuntimeError("Este video no tiene pista de audio, no hay música que quitar.")
        if not c["q_ini"] or not c["q_fin"]:
            raise RuntimeError("Escribe el inicio y el fin del tramo a quitar.")

        ini, fin = a_segundos(c["q_ini"]), a_segundos(c["q_fin"])
        total = duracion(ruta)
        if not (0 < ini < fin < total):
            raise RuntimeError(
                f"El tramo debe estar en medio del video (0 a {total:.1f} s) "
                "y el inicio debe ser menor que el fin.")

        # El fundido no puede ser más largo que el trozo más corto
        f = min(float(c["q_fade"]), ini, total - fin)

        fo_v = f",fade=t=out:st={ini - f:.3f}:d={f:.3f}" if f > 0 else ""
        fo_a = f",afade=t=out:st={ini - f:.3f}:d={f:.3f}" if f > 0 else ""
        fi_v = f",fade=t=in:st=0:d={f:.3f}" if f > 0 else ""
        fi_a = f",afade=t=in:st=0:d={f:.3f}" if f > 0 else ""

        filtro = (
            f"[0:v]trim=start=0:end={ini:.3f},setpts=PTS-STARTPTS{fo_v}[v0];"
            f"[0:a]atrim=start=0:end={ini:.3f},asetpts=PTS-STARTPTS{fo_a}[a0];"
            f"[0:v]trim=start={fin:.3f}:end={total:.3f},setpts=PTS-STARTPTS{fi_v}[v1];"
            f"[0:a]atrim=start={fin:.3f}:end={total:.3f},asetpts=PTS-STARTPTS{fi_a}[a1];"
            "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
        )

        base, _ = os.path.splitext(ruta)
        salida = f"{base}_sin_tramo.mp4"
        nueva = total - (fin - ini)
        self.after(0, lambda: self.barra.set(0))
        self.escribir(f"Quitando {fin - ini:.1f} s... el resultado durará {nueva / 60:.1f} min.")
        self.escribir("Recodifica todo el video, puede tardar un rato.")

        subprocess.run(
            ["ffmpeg", "-y", "-i", ruta, "-filter_complex", filtro,
             "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-crf", c["q_crf"], "-preset", "slow",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", salida],
            check=True, capture_output=True, text=True, errors="replace",
            creationflags=NO_WINDOW)

        self.after(0, lambda: self.barra.set(1))
        self.escribir(f"  OK -> {os.path.basename(salida)}")
        self.escribir("Listo.")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    App().mainloop()