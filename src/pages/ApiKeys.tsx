import { useMemo, useState } from 'react'
import { api, type ApiKey } from '../lib/api'
import { useAsync, usePaged } from '../lib/useAsync'
import { useProject, useT, useToast, useLang } from '../lib/store'
import { Dialog, Pager, Panel, PageHeader, PrimaryButton, StateRow, Table, TD, TD_BREAK, Th, TextLinkButton } from '../components/ui'
import { RowActions } from '../components/ui/row-actions'
import { Icon } from '../components/Icon'
import { copyText } from '../lib/clipboard'
import { errText } from '../lib/i18n'

import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

/** 密钥展示截断：前 7 位 + 7 个星号 + 后 8 位 */
const mask = (key: string) => (key ? `${key.substring(0, 7)}*******${key.substring(key.length - 8)}` : '')

/** 校验消息也走字典：硬编码中文在英文界面里会冒出来（AGENTS 第 3 条）。 */
const makeCreateKeySchema = (t: ReturnType<typeof useT>) =>
  z.object({
    name: z.string().min(1, t('apikeys.nameRequired')).max(64, t('apikeys.nameTooLong')),
  })

type CreateKeyForm = z.infer<ReturnType<typeof makeCreateKeySchema>>

export function ApiKeys() {
  const t = useT()
  const { lang } = useLang()
  const toast = useToast()
  const pg = usePaged(10)
  const { currentProjectId, ready } = useProject()
  const { data, state, error, reload } = useAsync(
    () => api.keys.list(currentProjectId, pg.page, pg.pageSize),
    [currentProjectId, pg.page, pg.pageSize],
    { skip: !ready },
  )

  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<ApiKey | null>(null)
  const [pendingDelete, setPendingDelete] = useState<ApiKey | null>(null)
  const [renaming, setRenaming] = useState<ApiKey | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateKeyForm>({
    resolver: zodResolver(useMemo(() => makeCreateKeySchema(t), [t])),
    defaultValues: { name: '' },
  })

  const copy = async (text: string) => {
    try {
      await copyText(text)
      toast(t('common.copied'))
    } catch {
      toast(t('common.copyFailed'), 'err')
    }
  }

  const submitCreate = handleSubmit(async (values) => {
    try {
      const k = await api.keys.create(currentProjectId, values.name.trim())
      setCreating(false)
      reset()
      setCreated(k)
      reload()
    } catch (e) {
      toast(errText(lang, e), 'err')
    }
  })

  const doDelete = async () => {
    if (!pendingDelete) return
    const target = pendingDelete
    setPendingDelete(null)
    try {
      await api.keys.revoke(target.id)
      toast(t('apikeys.deleted')(target.keyName))
      reload()
    } catch (e) {
      toast(errText(lang, e), 'err')
    }
  }

  const doRename = async () => {
    if (!renaming) return
    const name = renameValue.trim()
    if (!name) {
      toast(t('apikeys.nameRequired'), 'err')
      return
    }
    try {
      await api.keys.rename(renaming.id, name)
      setRenaming(null)
      toast(t('apikeys.renamed'))
      reload()
    } catch (e) {
      toast(errText(lang, e), 'err')
    }
  }

  const noProject = ready && !currentProjectId

  return (
    <>
      <PageHeader
        title={t('apikeys.title')}
        actions={
          <PrimaryButton icon="i-lucide:plus" disabled={noProject} onClick={() => setCreating(true)}>
            {t('apikeys.new')}
          </PrimaryButton>
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <div className="flex-1">
          <div className="flex h-full min-h-0 flex-col gap-3">
            <Panel className="flex-1 min-h-0">
              <Table
                head={
                  <>
                    <Th>{t('apikeys.col.name')}</Th>
                    <Th>{t('apikeys.col.key')}</Th>
                    <Th>{t('apikeys.col.createdAt')}</Th>
                    <Th>{t('apikeys.col.action')}</Th>
                  </>
                }
              >
                {noProject && <StateRow colSpan={4} state="error" error={t('apikeys.noProject')} />}
                {!noProject && state !== 'ready' && <StateRow colSpan={4} state={state} error={error} />}
                {!noProject && state === 'ready' && data?.records.length === 0 && (
                  <StateRow
                    colSpan={4}
                    state="ready"
                    emptyTitle={t('apikeys.empty')}
                    emptyAction={
                      <PrimaryButton icon="i-lucide:plus" onClick={() => setCreating(true)}>
                        {t('apikeys.new')}
                      </PrimaryButton>
                    }
                  />
                )}
                {!noProject &&
                  state === 'ready' &&
                  data?.records.map((k) => (
                    <tr key={k.id} data-selectable="true" className="data-[selected=true]:bg-elevated/50">
                      <td data-pinned="false" className={TD_BREAK}>
                        {k.keyName}
                      </td>
                      <td data-pinned="false" className={`${TD}`}>
                        <div className="font-mono text-sm">{mask(k.apiKey)}</div>
                      </td>
                      <td data-pinned="false" className={`${TD}`}>
                        {k.createTime}
                      </td>
                      <td data-pinned="false" className={`${TD}`}>
                        <RowActions
                          actions={[
                            {
                              label: t('apikeys.rename'),
                              icon: 'i-lucide:pencil',
                              onClick: () => {
                                setRenameValue(k.keyName)
                                setRenaming(k)
                              },
                            },
                            { label: t('apikeys.delete'), icon: 'i-lucide:trash-2', tone: 'danger', onClick: () => setPendingDelete(k) },
                          ]}
                        />
                      </td>
                    </tr>
                  ))}
              </Table>
            </Panel>

            <Pager page={pg.page} pageSize={pg.pageSize} total={data?.total ?? 0} onPage={pg.setPage} />
          </div>
        </div>
      </div>

      <Dialog open={creating} title={t('apikeys.addApikey')} onClose={() => setCreating(false)}>
        <form className="space-y-4" onSubmit={submitCreate}>
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-ink-secondary">{t('apikeys.dialog.name')}</label>
            <Input autoFocus {...register('name')} error={!!errors.name} placeholder={t('apikeys.dialog.namePlaceholder')} />
            {errors.name && <p className="text-xs text-danger font-medium">{errors.name.message}</p>}
          </div>
          <div className="flex justify-end gap-2.5 pt-2">
            <Button type="button" variant="secondary" onClick={() => setCreating(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>
              {t('common.create')}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={!!created}
        title={t('apikeys.addApikey')}
        onClose={() => setCreated(null)}
        footer={<PrimaryButton onClick={() => setCreated(null)}>{t('apikeys.dialog.done')}</PrimaryButton>}
      >
        <p className="mb-3 text-ink-muted">{t('apikeys.dialog.created')}</p>
        {/* ⚠️ 这句必须有：接口返回成功只代表**配置写进去了**，网关是启动时读环境变量的，
            没重启之前这把密钥在网关侧根本不存在（2026-10-19 实测新建后立刻拿它请求，
            网关回 401 invalid_token）。不写这句，用户会以为「建好了就能用」。 */}
        <p className="mb-3 text-warning">{t('apikeys.createdNotice')}</p>
        <div className="flex items-center gap-2 rounded-[8px] bg-surface-muted border border-line px-3 py-2">
          <code className="flex-1 font-mono text-xs break-all text-ink">{created?.apiKey}</code>
          <TextLinkButton onClick={() => copy(created?.apiKey ?? '')}>
            <Icon name="i-lucide:copy" className="shrink-0 size-4" />
            {t('apikeys.dialog.copy')}
          </TextLinkButton>
        </div>
      </Dialog>

      <Dialog
        open={!!renaming}
        title={t('apikeys.renameTitle')}
        onClose={() => setRenaming(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenaming(null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="primary" onClick={doRename}>
              {t('common.save')}
            </Button>
          </>
        }
      >
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-ink-secondary">{t('apikeys.dialog.name')}</label>
          <Input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            placeholder={t('apikeys.dialog.namePlaceholder')}
          />
          <p className="text-xs text-ink-muted">{t('apikeys.renameHint')}</p>
        </div>
      </Dialog>

      <Dialog
        open={!!pendingDelete}
        title={t('apikeys.deleteApikey')}
        onClose={() => setPendingDelete(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={doDelete}>
              {t('common.delete')}
            </Button>
          </>
        }
      >
        {t('apikeys.confirmDelete')(pendingDelete?.keyName ?? '')}
      </Dialog>
    </>
  )
}
