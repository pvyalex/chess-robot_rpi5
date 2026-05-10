import cv2
import time

def GenerarePoze(img_name):
    # Deschide camera (0 = implicită; schimbă la 1 dacă ai mai multe)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Nu am putut deschide camera.")
        return

    print("📷 Camera pornită. Apasă SPACE pentru poză, ESC pentru ieșire...")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Nu pot citi frame-ul de la cameră.")
            break

        cv2.imshow("Camera - apasa SPACE pentru poza, ESC pentru iesire", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC pentru ieșire
            print("🚪 Ieșire fără salvare.")
            break
        elif key == 32:  # SPACE pentru poza
            cv2.imwrite(img_name, frame)
            print(f"✅ Poza salvată ca '{img_name}'")
            break

    cap.release()
    cv2.destroyAllWindows()


def GenerarePozaAutomata(img_name, delay=10):
   
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ Nu am putut deschide camera.")
        return False

    print(f"📷 Camera pornită. Poza se va face automat în {delay} secunde...")
    
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Nu pot citi frame-ul de la cameră.")
            cap.release()
            cv2.destroyAllWindows()
            return False

        # Calculate remaining time
        elapsed = time.time() - start_time
        remaining = max(0, delay - elapsed)
        
        # Display countdown on frame
        display_frame = frame.copy()
        cv2.putText(display_frame, f"Poza in: {remaining:.1f}s", (10, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
        cv2.imshow("Camera - poza automata (ESC pentru anulare)", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC pentru anulare
            print("🚪 Anulat de utilizator.")
            cap.release()
            cv2.destroyAllWindows()
            return False

        # Take photo after delay
        if elapsed >= delay:
            cv2.imwrite(img_name, frame)
            print(f"✅ Poza salvată automat ca '{img_name}'")
            break

    cap.release()
    cv2.destroyAllWindows()
    return True

#GenerarePoze('Calibrare.jpg')  