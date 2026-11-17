/* SPDX-License-Identifier: MIT
 * liuqin 的 22H374 启动诊断：避免 lsd 在缺少无线控制器时阻塞。
 * 仅跳过设备树查询之后的同步控制器搜索，保留系统自身的备用路径。
 */
static void liuqin_mg_wifi_image(const struct mach_header *header,intptr_t slide)
{
    static bool installed;
    static const uint8_t uuid[16]={0xbe,0xed,0x77,0xde,0x98,0x7a,0x34,0x7e,
                                  0xad,0xa9,0x88,0x63,0x4a,0x6b,0xe5,0x6a};
    if(installed || !header || header->magic!=MH_MAGIC_64)return;
    const struct mach_header_64 *h=(const void *)header;
    const struct load_command *lc=(const void *)(h+1);
    const char *end=(const char *)lc+h->sizeofcmds;
    bool matched=false;
    for(uint32_t i=0;i<h->ncmds;i++) {
        if((const char *)lc+sizeof(*lc)>end || lc->cmdsize<sizeof(*lc) ||
           lc->cmdsize>(size_t)(end-(const char *)lc))return;
        if(lc->cmd==LC_UUID && lc->cmdsize==sizeof(struct uuid_command) &&
           !memcmp(((const struct uuid_command *)lc)->uuid,uuid,sizeof(uuid)))matched=true;
        lc=(const void *)((const char *)lc+lc->cmdsize);
    }
    if(!matched)return;
    /* 保留相邻的条件分支，只将同步搜索调用改为返回空结果。 */
    static const uint32_t expected[]={0x3707fcc0,0x94004650,0xb5ffff60};
    static const uint32_t replacement[]={0x3707fcc0,0xd2800000,0xb5ffff60};
    installed=install_compositor_code(header,slide,0x19440,expected,replacement,
                                      sizeof(expected),"liuqin lsd WLAN wait");
}
