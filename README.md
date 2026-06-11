# vangrapf-cli
Vangrapf CLI, для просмотра видео с Rutube, YouTube, VK Video, Ok и других без рекламы и ограничений с возможностью загрузки

# Использование

Легко смотреть видео с ютуба (должен быть установлен FFMPEG и mpv):

    python3 main.py --watch https://www.youtube.com/watch?v=enNy7_eu6GQ 

<img width="1894" height="681" alt="Снимок экрана_20260611_233913" src="https://github.com/user-attachments/assets/a796ede4-316e-4191-a964-6d590bdeae10" />


Легкая загрузка видео:

    python3 main.py --download https://www.youtube.com/watch?v=enNy7_eu6GQ

<img width="911" height="101" alt="Снимок экрана_20260611_234313" src="https://github.com/user-attachments/assets/e5a4abf6-2655-4106-9f29-f2d99005c930" />



Легкий поиск по YouTube:

    python3 main.py --search "Mellstroy интервью вписка" --api-key <Your YouTube Data VPI v3>

<img width="933" height="378" alt="Снимок экрана_20260611_234710" src="https://github.com/user-attachments/assets/e2ece8c8-409f-40fb-aab4-372325505796" />



Легкий поиск по YouTube (с возможностью просмотра видео):

    python3 main.py --watch --search "Mellstroy интервью вписка" --api-key <Your YouTube Data VPI v3>

<img width="952" height="767" alt="Снимок экрана_20260611_234902" src="https://github.com/user-attachments/assets/3267a36f-f7fc-4f90-8436-9321a0d62b3f" />
