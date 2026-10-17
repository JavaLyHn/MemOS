import { useState } from 'react'
import { api, type ApiKey } from '../lib/api'
import { useAsync, usePaged } from '../lib/useAsync'
import { useProject, useT, useToast } from '../lib/store'
import { Dialog, Pager, Panel, PageHeader, PrimaryButton, StateRow, Table, TD, TD_BREAK, Th, TextLinkButton } from '../components/ui'
import { BTN_DIALOG_PRIMARY, BTN_DIALOG_SECONDARY, DIALOG_INPUT, DIALOG_LABEL } from '../lib/cls'
import { Icon } from '../components/Icon'

/** 密钥展示截断：前 7 位 + 7 个星号 + 后 8 位 */
const mask = (key: string) => (key ? `${key.substring(0, 7)}*******${key.substring(key.length - 8)}` : '')

export function ApiKeys() {
  const t = useT()
  const toast = useToast()
  const pg = usePaged(10)
  const { currentProjectId, loading: projectLoading } = useProject()
  const { data, state, error, reload } = useAsync(
    () => api.keys.list(currentProjectId, pg.page, pg.pageSize),
    [currentProjectId, pg.page, pg.pageSize],
  )

  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState<ApiKey | null>(null)
  const [pendingDelete, setPendingDelete] = useState<ApiKey | null>(null)

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast(t('common.copied'))
    } catch {
      toast(`${t('common.failed')}：剪贴板不可用`, 'err')
    }
  }

  /** 复制走独立接口，拿到的是完整密钥 */
  const copyKey = async (id: string) => {
    try {
      copy(await api.keys.copy(id))
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'err')
    }
  }

  const submitCreate = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      const k = await api.keys.create(currentProjectId, name.trim())
      setCreating(false)
      setName('')
      setCreated(k)
      reload()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'err')
    } finally {
      setBusy(false)
    }
  }

  const doDelete = async () => {
    if (!pendingDelete) return
    const target = pendingDelete
    setPendingDelete(null)
    try {
      await api.keys.revoke(target.id)
      toast(`${t('common.delete')}：${target.keyName}`)
      reload()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'err')
    }
  }

  const noProject = !projectLoading && !currentProjectId

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

      <div className="flex flex-col flex-1 space-y-4 h-full">
        <div className="flex-1">
          <div className="h-full flex flex-col justify-between">
            <Panel>
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
                {!noProject && state === 'ready' && data?.records.length === 0 && <StateRow colSpan={4} state="ready" />}
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
                        <div className="flex gap-2">
                          <TextLinkButton onClick={() => copyKey(k.id)}>{t('apikeys.copy')}</TextLinkButton>
                          <TextLinkButton onClick={() => setPendingDelete(k)}>{t('apikeys.delete')}</TextLinkButton>
                        </div>
                      </td>
                    </tr>
                  ))}
              </Table>
            </Panel>

            <Pager page={pg.page} pageSize={pg.pageSize} total={data?.total ?? 0} onPage={pg.setPage} />
          </div>
        </div>
      </div>

      <Dialog
        open={creating}
        title={t('apikeys.addApikey')}
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className={BTN_DIALOG_PRIMARY} onClick={submitCreate} disabled={!name.trim() || busy}>
              {t('common.create')}
            </button>
            <button type="button" className={BTN_DIALOG_SECONDARY} onClick={() => setCreating(false)}>
              {t('common.cancel')}
            </button>
          </>
        }
      >
        <form className="space-y-5" onSubmit={(e) => e.preventDefault()}>
          <div className="text-sm">
            <div>
              <div className="flex content-center items-center justify-between">
                <label className={DIALOG_LABEL}>{t('apikeys.dialog.name')}</label>
              </div>
              <div className="relative mt-1.5">
                <div className="relative inline-flex items-center group w-full">
                  <input
                    autoFocus
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && submitCreate()}
                    placeholder={t('apikeys.dialog.namePlaceholder')}
                    className={DIALOG_INPUT}
                  />
                </div>
              </div>
            </div>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={!!created}
        title={t('apikeys.addApikey')}
        onClose={() => setCreated(null)}
        footer={<PrimaryButton onClick={() => setCreated(null)}>{t('apikeys.dialog.done')}</PrimaryButton>}
      >
        <p className="mb-3 text-[#62748E]">{t('apikeys.dialog.created')}</p>
        <div className="flex items-center gap-2 rounded-[8px] bg-[#f7f8fb] border border-[#E2E8F0] px-3 py-2">
          <code className="flex-1 font-mono text-xs break-all text-[#18181b]">{created?.apiKey}</code>
          <TextLinkButton onClick={() => copy(created?.apiKey ?? '')}>
            <Icon name="i-lucide:copy" className="shrink-0 size-4" />
            {t('apikeys.dialog.copy')}
          </TextLinkButton>
        </div>
      </Dialog>

      <Dialog
        open={!!pendingDelete}
        title={t('apikeys.deleteApikey')}
        onClose={() => setPendingDelete(null)}
        footer={
          <>
            <button type="button" className={BTN_DIALOG_PRIMARY} onClick={doDelete}>
              {t('common.confirm')}
            </button>
            <button type="button" className={BTN_DIALOG_SECONDARY} onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </button>
          </>
        }
      >
        {t('apikeys.confirmDelete')(pendingDelete?.keyName ?? '')}
      </Dialog>
    </>
  )
}
