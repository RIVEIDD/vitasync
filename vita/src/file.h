#ifndef __FILE_H__
#define __FILE_H__

int exists(const char *path);
int is_dir(const char *path);

int mkdir_p(const char *path, int mode);
int rmdir_r(const char *path, void (*callback)());
int file_count(char *path, int check_blacklist);
int copydir(const char *src, const char *dest, void (*callback)());

int copyfile(char *src, char *dest);
#endif
