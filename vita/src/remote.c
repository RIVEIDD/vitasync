#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <psp2/sysmodule.h>

#include <ftpvita.h>

#include "common.h"
#include "config.h"
#include "file.h"
#include "input.h"
#include "remote.h"
#include "system.h"
#include "util.h"

static volatile int busy = 0;
static char status[128] = "";

int remote_busy() {
    return busy;
}

const char *remote_status() {
    return status;
}

// Dossier de la sauvegarde d'un jeu, comme save_dir_path() dans main.c.
static char *save_path(const char *titleid) {
    char *path = calloc(sizeof(char), 1);
    aprintf(&path, "grw0:savedata/%s", titleid);
    if (exists(path)) {
        return path;
    }
    free(path);
    path = calloc(sizeof(char), 1);
    aprintf(&path, "ux0:user/00/savedata/%s", titleid);
    if (exists(path)) {
        return path;
    }
    free(path);
    return NULL;
}

// Dossier d'un slot, comme slot_dir_path() dans main.c.
static char *slot_path(const char *titleid, int slot) {
    char *fmt = calloc(sizeof(char), 1);
    char *path = calloc(sizeof(char), 1);
    aprintf(&fmt, "%s/%s", config.base, config.slot_format);
    aprintf(&path, fmt, titleid, slot);
    free(fmt);
    return path;
}

// Lit "<TITLEID> <slot>" ; renvoie 0 si les arguments sont valides.
static int parse_args(const char *args, char *titleid, int *slot) {
    if (!args || sscanf(args, "%9s %d", titleid, slot) != 2) {
        return -1;
    }
    if (strlen(titleid) != 9 || *slot < 0 || *slot > 9) {
        return -1;
    }
    return 0;
}

static void reply(ftpvita_client_info_t *client, const char *msg) {
    snprintf(status, sizeof(status), "%s", msg);
    char line[160];
    snprintf(line, sizeof(line), "%s" FTPVITA_EOL, msg);
    ftpvita_ext_client_send_ctrl_msg(client, line);
}

// Copie src -> dest avec la sauvegarde montée décryptée (mount_path).
// Renvoie un message de réponse FTP (code 200 ou 550).
static const char *copy_mounted(const char *mount_path, const char *src, const char *dest,
                                int fix_account) {
    const char *result = "200 OK";
    lock_psbutton();
    if (pfs_mount(mount_path) < 0) {
        result = "550 Impossible de decrypter la sauvegarde";
        goto exit;
    }
    mkdir_p(dest, 0777);
    if (copydir(src, dest, NULL) <= 0) {
        result = "550 Echec de la copie";
        goto exit;
    }
    if (fix_account) {
        char *sfo = calloc(sizeof(char), 1);
        aprintf(&sfo, "%s/sce_sys/param.sfo", dest);
        if (exists(sfo)) {
            change_accountid(sfo, get_accountid());
        }
        free(sfo);
    }
exit:
    pfs_unmount();
    unlock_psbutton();
    return result;
}

static void run(ftpvita_client_info_t *client, int restore) {
    char titleid[10] = {0};
    int slot = 0;
    if (parse_args(client->recv_cmd_args, titleid, &slot) < 0) {
        reply(client, "501 Usage : VSBK|VSRS <TITLEID> <slot 0-9>");
        return;
    }
    if (busy) {
        reply(client, "450 Une autre commande est en cours");
        return;
    }
    busy = 1;
    snprintf(status, sizeof(status), "%s %s slot %d...", restore ? "Restore" : "Backup",
             titleid, slot);

    char *save = save_path(titleid);
    char *slot_dir = slot_path(titleid, slot);
    if (!save) {
        reply(client, "550 Sauvegarde introuvable : lance le jeu une fois");
    } else if (restore && !exists(slot_dir)) {
        reply(client, "550 Slot vide");
    } else if (restore) {
        reply(client, copy_mounted(save, slot_dir, save, 1));
    } else {
        reply(client, copy_mounted(save, save, slot_dir, 0));
    }
    free(save);
    free(slot_dir);
    busy = 0;
}

static void cmd_VSBK(ftpvita_client_info_t *client) {
    run(client, 0);
}

static void cmd_VSRS(ftpvita_client_info_t *client) {
    run(client, 1);
}

static void cmd_VSVR(ftpvita_client_info_t *client) {
    // Pas de reply() : cette question du PC ne doit pas remplacer l'état affiché.
    ftpvita_ext_client_send_ctrl_msg(client, "200 VitaSync " VERSION FTPVITA_EOL);
}

int remote_start(char *ip, unsigned short *port) {
    sceSysmoduleLoadModule(SCE_SYSMODULE_NET);
    int res = ftpvita_init(ip, port);
    if (res < 0) {
        snprintf(status, sizeof(status), "FTP indisponible (0x%08X) : Wi-Fi ?", res);
        return res;
    }
    ftpvita_add_device("ux0:");
    ftpvita_add_device("ur0:");
    ftpvita_add_device("uma0:");
    ftpvita_add_device("grw0:");
    ftpvita_ext_add_custom_command("VSBK", cmd_VSBK);
    ftpvita_ext_add_custom_command("VSRS", cmd_VSRS);
    ftpvita_ext_add_custom_command("VSVR", cmd_VSVR);
    snprintf(status, sizeof(status), "FTP pret : %s:%u", ip, *port);
    return 0;
}

void remote_stop() {
    if (ftpvita_is_initialized()) {
        ftpvita_fini();
    }
}
