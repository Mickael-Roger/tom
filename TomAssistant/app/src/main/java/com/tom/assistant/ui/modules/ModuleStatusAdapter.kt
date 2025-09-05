package com.tom.assistant.ui.modules

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.tom.assistant.R
import com.tom.assistant.models.ModuleStatus

class ModuleStatusAdapter(
    private val onModuleClick: (ModuleStatus) -> Unit
) : RecyclerView.Adapter<ModuleStatusAdapter.ModuleStatusViewHolder>() {

    private val modules = mutableListOf<ModuleStatus>()

    fun updateModules(newModules: List<ModuleStatus>) {
        modules.clear()
        modules.addAll(newModules)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ModuleStatusViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_module_status, parent, false)
        return ModuleStatusViewHolder(view)
    }

    override fun onBindViewHolder(holder: ModuleStatusViewHolder, position: Int) {
        holder.bind(modules[position])
    }

    override fun getItemCount(): Int = modules.size

    inner class ModuleStatusViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val tvModuleName: TextView = itemView.findViewById(R.id.tvModuleName)

        fun bind(module: ModuleStatus) {
            tvModuleName.text = module.name
            
            // Set background color based on status
            val backgroundColor = if (module.status == "connected") {
                ContextCompat.getColor(itemView.context, R.color.status_connected)
            } else {
                ContextCompat.getColor(itemView.context, R.color.status_error)
            }
            
            itemView.setBackgroundColor(backgroundColor)
            
            // Set click listener
            itemView.setOnClickListener {
                onModuleClick(module)
            }
        }
    }
}