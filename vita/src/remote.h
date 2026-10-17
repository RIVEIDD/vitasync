#ifndef __REMOTE_H__
#define __REMOTE_H__

// Serveur FTP intégré à VitaSync, actif seulement pendant que l'appli tourne.
// En plus des commandes FTP habituelles, il accepte :
//   VSVR                 -> "200 VitaSync <version>"
//   VSBK <TITLEID> <n>   -> sauvegarde décryptée de <TITLEID> copiée dans le slot <n>
//   VSRS <TITLEID> <n>   -> slot <n> remis dans la sauvegarde de <TITLEID>
// Les slots sont ceux de Save Manager : <config.base>/<config.slot_format>.

// Démarre le serveur ; renvoie 0 si tout va bien. ip doit faire 16 octets.
int remote_start(char *ip, unsigned short *port);
void remote_stop();

// Vrai pendant qu'une commande VSBK/VSRS s'exécute.
int remote_busy();
// Dernier message à afficher (commande en cours ou résultat), jamais NULL.
const char *remote_status();

#endif
