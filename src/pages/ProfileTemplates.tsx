import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ProfileTemplate } from '../lib/api'
import { ListPage } from '../components/ListPage'
import { Dialog, TextLinkButton } from '../components/ui'
import { BTN_DIALOG_PRIMARY, BTN_DIALOG_SECONDARY, BTN_PRIMARY, BTN_TEXT_LINK } from '../lib/cls'
import { useProject, useT, useToast } from '../lib/store'

export function ProfileTemplates() {
  const t = useT()
  const toast = useToast()
  const { currentProjectId } = useProject()
  const [pendingDelete, setPendingDelete] = useState<ProfileTemplate | null>(null)
  const [tick, setTick] = useState(0)

  const doDelete = async () => {
    if (!pendingDelete) return
    const target = pendingDelete
    setPendingDelete(null)
    try {
      await api.profileTemplate.remove(currentProjectId, target.templateId)
      toast(t('profile.action.delete'))
      setTick((n) => n + 1)
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'err')
    }
  }

  return (
    <>
      <ListPage<ProfileTemplate>
        title={t('profile.title')}
        desc={t('profile.desc')}
        rowKey={(p) => p.templateId}
        deps={[currentProjectId, tick]}
        actions={
          <Link to="/cn/profileTemplate/new" className={`${BTN_PRIMARY} cursor-pointer`}>
            <span className="iconify i-lucide:plus shrink-0 size-5" aria-hidden="true" />
            {t('profile.newTemplate')}
          </Link>
        }
        load={async (pageNum, pageSize) => {
          const res = await api.profileTemplate.list(pageNum, pageSize, currentProjectId)
          return { items: res.list, total: res.total }
        }}
        cols={[
          { key: 'templateName', label: t('profile.col.templateName'), wrap: true, render: (p) => p.templateName },
          { key: 'templateId', label: t('profile.col.templateId'), wrap: true, render: (p) => p.templateId },
          { key: 'bindingCount', label: t('profile.col.bindingCount'), render: (p) => String(p.bindingCount ?? 0) },
          { key: 'updatedAt', label: t('profile.col.updatedAt'), render: (p) => p.updatedAt ?? '-' },
          {
            key: 'action',
            label: t('profile.col.action'),
            render: (p) => (
              <div className="flex gap-2">
                <Link to={`/cn/profileTemplate/${p.templateId}`} className={BTN_TEXT_LINK}>
                  {t('profile.action.view')}
                </Link>
                <TextLinkButton onClick={() => setPendingDelete(p)}>{t('profile.action.delete')}</TextLinkButton>
              </div>
            ),
          },
        ]}
      />

      <Dialog
        open={!!pendingDelete}
        title={t('profile.delete.title')}
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
        {t('profile.delete.confirm')}
      </Dialog>
    </>
  )
}
