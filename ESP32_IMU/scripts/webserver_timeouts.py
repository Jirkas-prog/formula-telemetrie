"""Pinned Arduino 2.0.17 multipart parser otherwise waits forever on a stalled client."""
from pathlib import Path
Import('env')
source = Path(env.PioPlatform().get_package_dir('framework-arduinoespressif32')) / 'libraries/WebServer/src/Parsing.cpp'
text = source.read_text(encoding='utf-8')
old = '''    while(!client.available() && client.connected())
      delay(2);'''
new = '''    // IMU: idle timeout, not a limit on the duration of a large upload.
    uint32_t lastByte = millis();
    while(!client.available() && client.connected()) {
      if (millis() - lastByte > 30000) { client.stop(); return -1; }
      delay(2);
    }'''
if new not in text:
    if text.count(old) != 1:
        raise RuntimeError('Unexpected WebServer parser; review the idle-timeout patch before building.')
    source.write_text(text.replace(old, new), encoding='utf-8')
